import dataclasses
import datetime
import pickle
from pathlib import Path

import pandas as pd
from sklearn.metrics import mean_absolute_error
from sqlalchemy.orm import Session
from xgboost import XGBRegressor

from src.db.models import Game, ModelPrediction, Player, PlayerGameStats
from src.features import player_features, team_features
from src.ingestion.nba_stats import NBA_TEAM_NAMES

_FULL_TO_ABBR: dict[str, str] = {v: k for k, v in NBA_TEAM_NAMES.items()}

MODEL_VERSION = "xgb_props_v1"

FEATURE_COLS: list[str] = [
    "rolling_points",
    "rolling_usage",
    "team_usage_lost",
    "opp_rolling_drtg",
    "is_home",
    "rest_days",
]

_FEATURE_FILL: dict[str, float] = {
    "rolling_points": 10.0,
    "rolling_usage": 15.0,
    "team_usage_lost": 0.0,
    "opp_rolling_drtg": 112.0,
    "is_home": 0.0,
    "rest_days": 3.0,
}

_DEFAULT_XGB: dict = dict(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1,
)


@dataclasses.dataclass
class PropsCVFold:
    cutoff: datetime.datetime
    n_train: int
    n_test: int
    mae: float
    coverage_80: float


@dataclasses.dataclass
class PropsModel:
    q10: XGBRegressor
    q50: XGBRegressor
    q90: XGBRegressor
    feature_cols: list[str]
    trained_as_of: datetime.datetime
    n_train: int

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        """Return DataFrame with columns p10, p50, p90 for each row."""
        Xf = X[self.feature_cols]
        return pd.DataFrame(
            {
                "p10": self.q10.predict(Xf),
                "p50": self.q50.predict(Xf),
                "p90": self.q90.predict(Xf),
            }
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path) -> "PropsModel":
        with open(path, "rb") as f:
            return pickle.load(f)


def _game_as_of(game: Game) -> datetime.datetime:
    """Midnight on game day — all pre-game data is available by then."""
    return datetime.datetime.combine(game.date, datetime.time(0, 0))


def _prep(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=FEATURE_COLS).fillna(_FEATURE_FILL).fillna(0.0)
    return df.astype(float)


def _player_is_home(player: Player, game: Game) -> bool:
    return NBA_TEAM_NAMES.get(player.team_abbreviation or "", "") == game.home_team


def _opp_abbr(player: Player, game: Game) -> str:
    opp_full = game.away_team if _player_is_home(player, game) else game.home_team
    return _FULL_TO_ABBR.get(opp_full, "")


def build_training_dataset(
    session: Session,
    as_of: datetime.datetime,
) -> tuple[pd.DataFrame, pd.Series]:
    """(X, y) for all player-games strictly before as_of where the player played.

    Processes in chronological order to compute per-player rest_days without
    O(n²) DB round-trips. Features are snapped to midnight on each game date
    (pre-game availability window).
    """
    qualifying = (
        session.query(PlayerGameStats, Game, Player)
        .join(Game, Game.id == PlayerGameStats.game_id)
        .join(Player, Player.id == PlayerGameStats.player_id)
        .filter(
            Game.status == "final",
            Game.date < as_of.date(),
            PlayerGameStats.minutes.isnot(None),
            PlayerGameStats.minutes > 0,
            PlayerGameStats.points.isnot(None),
        )
        .order_by(Game.date.asc(), PlayerGameStats.player_id.asc())
        .all()
    )

    last_game_date: dict[int, datetime.date] = {}
    feature_rows: list[dict] = []
    labels: list[float] = []

    for pgs, game, player in qualifying:
        game_as_of = _game_as_of(game)
        is_home = int(_player_is_home(player, game))
        opp = _opp_abbr(player, game)

        last_date = last_game_date.get(pgs.player_id)
        rest = (game.date - last_date).days if last_date is not None else 7

        feature_rows.append(
            {
                "rolling_points": player_features.rolling_points(
                    session, pgs.player_id, game.date, game_as_of
                ),
                "rolling_usage": player_features.rolling_usage(
                    session, pgs.player_id, game.date, game_as_of
                ),
                "team_usage_lost": player_features.team_usage_lost(
                    session, player.team_abbreviation or "", game.date, game_as_of
                ),
                "opp_rolling_drtg": team_features.rolling_drtg(session, opp, game.date, game_as_of),
                "is_home": is_home,
                "rest_days": rest,
            }
        )
        labels.append(float(pgs.points))
        last_game_date[pgs.player_id] = game.date

    return _prep(feature_rows), pd.Series(labels, dtype=float, name="points")


def _fit(
    X: pd.DataFrame,
    y: pd.Series,
    as_of: datetime.datetime,
    **xgb_kwargs: object,
) -> PropsModel:
    params = {**_DEFAULT_XGB, **xgb_kwargs}
    q10 = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.1, **params)
    q50 = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.5, **params)
    q90 = XGBRegressor(objective="reg:quantileerror", quantile_alpha=0.9, **params)
    q10.fit(X, y)
    q50.fit(X, y)
    q90.fit(X, y)
    return PropsModel(
        q10=q10,
        q50=q50,
        q90=q90,
        feature_cols=FEATURE_COLS,
        trained_as_of=as_of,
        n_train=len(X),
    )


def train(
    session: Session,
    as_of: datetime.datetime,
    min_samples: int = 100,
    **xgb_kwargs: object,
) -> PropsModel:
    """Train three quantile regressors (P10/P50/P90) on all player-games before as_of."""
    X, y = build_training_dataset(session, as_of)
    if len(X) < min_samples:
        raise ValueError(f"Insufficient training data: {len(X)} < {min_samples}")
    return _fit(X, y, as_of, **xgb_kwargs)


def walk_forward_cv(
    session: Session,
    cutoffs: list[datetime.datetime],
    test_days: int = 30,
    min_samples: int = 100,
    **xgb_kwargs: object,
) -> list[PropsCVFold]:
    """Walk-forward evaluation: train before each cutoff, test on the next window.

    No future data leaks into any training fold.
    Reports MAE of P50 and empirical coverage of the P10–P90 band (target ≈ 80%).
    """
    results: list[PropsCVFold] = []
    for cutoff in cutoffs:
        test_end = cutoff + datetime.timedelta(days=test_days)
        X_train, y_train = build_training_dataset(session, cutoff)
        if len(X_train) < min_samples:
            continue
        X_all, y_all = build_training_dataset(session, test_end)
        n_test = len(X_all) - len(X_train)
        if n_test == 0:
            continue
        model = _fit(X_train, y_train, cutoff, **xgb_kwargs)
        X_test = X_all.iloc[len(X_train) :]
        y_test = y_all.iloc[len(X_train) :]
        preds = model.predict(X_test)
        mae = float(mean_absolute_error(y_test, preds["p50"]))
        inside = (y_test.values >= preds["p10"].values) & (y_test.values <= preds["p90"].values)
        coverage = float(inside.mean())
        results.append(
            PropsCVFold(
                cutoff=cutoff,
                n_train=len(X_train),
                n_test=n_test,
                mae=mae,
                coverage_80=coverage,
            )
        )
    return results


def predict_player(
    session: Session,
    player: Player,
    game: Game,
    model: PropsModel,
    as_of: datetime.datetime,
    rest_days: int = 3,
) -> pd.DataFrame:
    """Return DataFrame with p10, p50, p90 for a single player in an upcoming game."""
    is_home = int(_player_is_home(player, game))
    opp = _opp_abbr(player, game)
    row = {
        "rolling_points": player_features.rolling_points(session, player.id, game.date, as_of),
        "rolling_usage": player_features.rolling_usage(session, player.id, game.date, as_of),
        "team_usage_lost": player_features.team_usage_lost(
            session, player.team_abbreviation or "", game.date, as_of
        ),
        "opp_rolling_drtg": team_features.rolling_drtg(session, opp, game.date, as_of),
        "is_home": is_home,
        "rest_days": rest_days,
    }
    return model.predict(_prep([row]))


def store_props_prediction(
    session: Session,
    game: Game,
    player: Player,
    p10: float,
    p50: float,
    p90: float,
    as_of: datetime.datetime,
) -> ModelPrediction:
    """Persist P50 (median) to model_predictions; P10/P90 band stored in features_json."""
    pred = ModelPrediction(
        game_id=game.id,
        market="player_points",
        selection=player.name,
        model_version=MODEL_VERSION,
        model_p=p50,
        features_json={"p10": round(p10, 2), "p90": round(p90, 2)},
        fetched_at=as_of,
        as_of=as_of,
    )
    session.add(pred)
    session.flush()
    return pred
