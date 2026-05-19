import dataclasses
import datetime
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, log_loss
from sqlalchemy.orm import Session
from xgboost import XGBClassifier

from src.db.models import Game, ModelPrediction
from src.features.builder import build_game_features
from src.ingestion.nba_stats import NBA_TEAM_NAMES
from src.models.elo import INITIAL_ELO, update_ratings

_FULL_TO_ABBR: dict[str, str] = {v: k for k, v in NBA_TEAM_NAMES.items()}

MODEL_VERSION = "xgb_moneyline_v1"

FEATURE_COLS: list[str] = [
    "home_rest_days",
    "away_rest_days",
    "home_is_b2b",
    "away_is_b2b",
    "home_travel_km",
    "away_travel_km",
    "home_rolling_pace",
    "away_rolling_pace",
    "home_rolling_ortg",
    "away_rolling_ortg",
    "home_rolling_drtg",
    "away_rolling_drtg",
    "home_usage_lost",
    "away_usage_lost",
    "home_elo",
    "away_elo",
]

# Fallback fill for rolling stats absent in early-season games
_FEATURE_FILL: dict[str, float] = {
    "home_rolling_pace": 100.0,
    "away_rolling_pace": 100.0,
    "home_rolling_ortg": 110.0,
    "away_rolling_ortg": 110.0,
    "home_rolling_drtg": 110.0,
    "away_rolling_drtg": 110.0,
}

_DEFAULT_XGB: dict = dict(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    eval_metric="logloss",
    random_state=42,
    n_jobs=-1,
)


@dataclasses.dataclass
class MoneylineModel:
    calibrated: CalibratedClassifierCV
    feature_cols: list[str]
    trained_as_of: datetime.datetime
    n_train: int

    def predict_proba_home(self, X: pd.DataFrame) -> np.ndarray:
        """P(home wins) for each row in X."""
        return self.calibrated.predict_proba(X[self.feature_cols])[:, 1]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path) -> "MoneylineModel":
        with open(path, "rb") as f:
            return pickle.load(f)


@dataclasses.dataclass
class CVFold:
    cutoff: datetime.datetime
    n_train: int
    n_test: int
    brier_score: float
    log_loss_val: float


def _game_as_of(game: Game) -> datetime.datetime:
    """Midnight on game day — all pre-game data is available by then."""
    return datetime.datetime.combine(game.date, datetime.time(0, 0))


def _to_row(gf: object, home_elo: float, away_elo: float) -> dict:
    d = gf.to_dict()  # type: ignore[attr-defined]
    d["home_elo"] = home_elo
    d["away_elo"] = away_elo
    d["home_is_b2b"] = int(d["home_is_b2b"])
    d["away_is_b2b"] = int(d["away_is_b2b"])
    return {col: d.get(col) for col in FEATURE_COLS}


def _prep(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=FEATURE_COLS).fillna(_FEATURE_FILL).fillna(0.0)
    return df.astype(float)


def build_training_dataset(
    session: Session,
    as_of: datetime.datetime,
) -> tuple[pd.DataFrame, pd.Series]:
    """(X, y) for all final games strictly before as_of.

    Games are processed in chronological order so Elo ratings accumulate
    without O(n²) DB round-trips.  Features are snapped to midnight on
    each game date (pre-game availability window).
    """
    games = (
        session.query(Game)
        .filter(
            Game.status == "final",
            Game.date < as_of.date(),
            Game.home_score.isnot(None),
            Game.away_score.isnot(None),
        )
        .order_by(Game.date.asc())
        .all()
    )

    rows: list[dict] = []
    labels: list[int] = []
    elos: dict[str, float] = {}

    for game in games:
        home_abbr = _FULL_TO_ABBR.get(game.home_team, "")
        away_abbr = _FULL_TO_ABBR.get(game.away_team, "")
        if not home_abbr or not away_abbr:
            continue
        h_elo = elos.get(home_abbr, INITIAL_ELO)
        a_elo = elos.get(away_abbr, INITIAL_ELO)
        gf = build_game_features(session, game, _game_as_of(game))
        rows.append(_to_row(gf, h_elo, a_elo))
        labels.append(1 if game.home_score > game.away_score else 0)
        # Advance running Elo AFTER recording the pre-game snapshot
        if game.home_score > game.away_score:
            elos[home_abbr], elos[away_abbr] = update_ratings(h_elo, a_elo)
        else:
            elos[away_abbr], elos[home_abbr] = update_ratings(a_elo, h_elo)

    return _prep(rows), pd.Series(labels, dtype=int, name="home_win")


def _fit(
    X: pd.DataFrame,
    y: pd.Series,
    as_of: datetime.datetime,
    cv: int = 5,
    **xgb_kwargs: object,
) -> MoneylineModel:
    params = {**_DEFAULT_XGB, **xgb_kwargs}
    base = XGBClassifier(**params)
    calibrated = CalibratedClassifierCV(base, method="isotonic", cv=cv)
    calibrated.fit(X, y)
    return MoneylineModel(
        calibrated=calibrated,
        feature_cols=FEATURE_COLS,
        trained_as_of=as_of,
        n_train=len(X),
    )


def train(
    session: Session,
    as_of: datetime.datetime,
    min_samples: int = 50,
    cv: int = 5,
    **xgb_kwargs: object,
) -> MoneylineModel:
    """Train XGBoost + isotonic calibration on all games before as_of."""
    X, y = build_training_dataset(session, as_of)
    if len(X) < min_samples:
        raise ValueError(f"Insufficient training data: {len(X)} < {min_samples}")
    return _fit(X, y, as_of, cv=cv, **xgb_kwargs)


def walk_forward_cv(
    session: Session,
    cutoffs: list[datetime.datetime],
    test_days: int = 30,
    min_samples: int = 50,
    cv: int = 5,
    **xgb_kwargs: object,
) -> list[CVFold]:
    """Walk-forward evaluation: train before each cutoff, test on the next window.

    No future data leaks into any training fold — each model sees only games
    strictly before its cutoff date.
    """
    results: list[CVFold] = []
    for cutoff in cutoffs:
        test_end = cutoff + datetime.timedelta(days=test_days)
        X_train, y_train = build_training_dataset(session, cutoff)
        if len(X_train) < min_samples:
            continue
        X_all, y_all = build_training_dataset(session, test_end)
        n_test = len(X_all) - len(X_train)
        if n_test == 0:
            continue
        model = _fit(X_train, y_train, cutoff, cv=cv, **xgb_kwargs)
        X_test = X_all.iloc[len(X_train) :]
        y_test = y_all.iloc[len(X_train) :]
        probs = model.predict_proba_home(X_test)
        results.append(
            CVFold(
                cutoff=cutoff,
                n_train=len(X_train),
                n_test=n_test,
                brier_score=float(brier_score_loss(y_test, probs)),
                log_loss_val=float(log_loss(y_test, probs)),
            )
        )
    return results


def predict_game(
    session: Session,
    game: Game,
    model: MoneylineModel,
    elos: dict[str, float],
    as_of: datetime.datetime,
) -> float:
    """Return calibrated P(home wins) for a single upcoming game."""
    home_abbr = _FULL_TO_ABBR.get(game.home_team, "")
    away_abbr = _FULL_TO_ABBR.get(game.away_team, "")
    h_elo = elos.get(home_abbr, INITIAL_ELO)
    a_elo = elos.get(away_abbr, INITIAL_ELO)
    gf = build_game_features(session, game, as_of)
    return float(model.predict_proba_home(_prep([_to_row(gf, h_elo, a_elo)]))[0])


def store_prediction(
    session: Session,
    game: Game,
    prob_home: float,
    as_of: datetime.datetime,
) -> ModelPrediction:
    """Persist a home-win probability to model_predictions."""
    pred = ModelPrediction(
        game_id=game.id,
        market="h2h",
        selection=game.home_team,
        model_version=MODEL_VERSION,
        model_p=prob_home,
        fetched_at=as_of,
        as_of=as_of,
    )
    session.add(pred)
    session.flush()
    return pred
