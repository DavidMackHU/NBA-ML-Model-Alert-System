import datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

import src.db.models  # noqa: F401 — registers all models with Base


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_: BigInteger, compiler: object, **kw: object) -> str:
    return "INTEGER"


from src.db.base import Base
from src.db.models import Game, ModelPrediction
from src.ingestion.nba_stats import NBA_TEAM_NAMES
from src.models.moneyline import (
    CVFold,
    FEATURE_COLS,
    MoneylineModel,
    build_training_dataset,
    predict_game,
    store_prediction,
    train,
    walk_forward_cv,
)


# ─── fixtures & helpers ───────────────────────────────────────────────────────


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def _dt(year: int, month: int, day: int, hour: int = 6) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour)


def _date(year: int, month: int, day: int) -> datetime.date:
    return datetime.date(year, month, day)


def _add_game(
    session: Session,
    game_date: datetime.date,
    home_abbr: str,
    away_abbr: str,
    home_score: int,
    away_score: int,
    gid: str | None = None,
) -> Game:
    g = Game(
        game_id=gid or f"{game_date}{home_abbr}{away_abbr}",
        date=game_date,
        home_team=NBA_TEAM_NAMES[home_abbr],
        away_team=NBA_TEAM_NAMES[away_abbr],
        tipoff_utc=_dt(game_date.year, game_date.month, game_date.day, 0),
        status="final",
        home_score=home_score,
        away_score=away_score,
        fetched_at=_dt(game_date.year, game_date.month, game_date.day),
        as_of=_dt(game_date.year, game_date.month, game_date.day),
    )
    session.add(g)
    session.flush()
    return g


def _add_upcoming(
    session: Session,
    game_date: datetime.date,
    home_abbr: str,
    away_abbr: str,
    gid: str | None = None,
) -> Game:
    g = Game(
        game_id=gid or f"upc{game_date}{home_abbr}",
        date=game_date,
        home_team=NBA_TEAM_NAMES[home_abbr],
        away_team=NBA_TEAM_NAMES[away_abbr],
        tipoff_utc=_dt(game_date.year, game_date.month, game_date.day, 0),
        status="scheduled",
        home_score=None,
        away_score=None,
        fetched_at=_dt(game_date.year, game_date.month, game_date.day),
        as_of=_dt(game_date.year, game_date.month, game_date.day),
    )
    session.add(g)
    session.flush()
    return g


def _populate_games(session: Session, n: int, start: datetime.date) -> None:
    """Add n BOS-vs-LAL games from start, alternating home win / away win."""
    base = datetime.date(start.year, start.month, start.day)
    for i in range(n):
        d = base + datetime.timedelta(days=i)
        if i % 2 == 0:
            _add_game(session, d, "BOS", "LAL", 110, 100, gid=f"g{i}")  # home win
        else:
            _add_game(session, d, "BOS", "LAL", 95, 110, gid=f"g{i}")  # away win
    session.commit()


# ─── build_training_dataset tests ────────────────────────────────────────────


def test_build_training_dataset_correct_shape(db: Session) -> None:
    _populate_games(db, 5, _date(2024, 1, 1))
    X, y = build_training_dataset(db, _dt(2024, 2, 1))
    assert X.shape == (5, len(FEATURE_COLS))
    assert len(y) == 5


def test_build_training_dataset_labels_match_scores(db: Session) -> None:
    _add_game(db, _date(2024, 1, 10), "BOS", "LAL", 110, 100, gid="hw")  # home wins → 1
    _add_game(db, _date(2024, 1, 11), "BOS", "LAL", 95, 110, gid="aw")  # away wins → 0
    db.commit()

    _, y = build_training_dataset(db, _dt(2024, 2, 1))
    assert list(y) == [1, 0]


def test_build_training_dataset_excludes_game_on_as_of_date(db: Session) -> None:
    _add_game(db, _date(2024, 1, 15), "BOS", "LAL", 110, 100)
    db.commit()

    X, _ = build_training_dataset(db, _dt(2024, 1, 15))
    assert len(X) == 0


def test_build_training_dataset_excludes_games_without_scores(db: Session) -> None:
    g = Game(
        game_id="noscr",
        date=_date(2024, 1, 10),
        home_team=NBA_TEAM_NAMES["BOS"],
        away_team=NBA_TEAM_NAMES["LAL"],
        tipoff_utc=_dt(2024, 1, 10, 0),
        status="scheduled",
        home_score=None,
        away_score=None,
        fetched_at=_dt(2024, 1, 10),
        as_of=_dt(2024, 1, 10),
    )
    db.add(g)
    db.commit()

    X, _ = build_training_dataset(db, _dt(2024, 2, 1))
    assert len(X) == 0


def test_build_training_dataset_elo_increases_for_winning_streak(db: Session) -> None:
    # BOS wins three home games against different opponents
    _add_game(db, _date(2024, 1, 1), "BOS", "LAL", 110, 100, gid="w1")
    _add_game(db, _date(2024, 1, 2), "BOS", "MIA", 110, 100, gid="w2")
    _add_game(db, _date(2024, 1, 3), "BOS", "GSW", 110, 100, gid="w3")
    db.commit()

    X, _ = build_training_dataset(db, _dt(2024, 2, 1))
    # home_elo at game time reflects wins so far — must be strictly increasing
    assert X["home_elo"].iloc[0] < X["home_elo"].iloc[1] < X["home_elo"].iloc[2]


# ─── train tests ─────────────────────────────────────────────────────────────


@pytest.fixture()
def trained_model(db: Session) -> MoneylineModel:
    _populate_games(db, 60, _date(2024, 1, 1))
    return train(db, _dt(2024, 5, 1), min_samples=10, cv=2, n_estimators=5)


def test_train_returns_moneyline_model(trained_model: MoneylineModel) -> None:
    assert isinstance(trained_model, MoneylineModel)


def test_train_records_n_train(trained_model: MoneylineModel) -> None:
    assert trained_model.n_train == 60


def test_train_raises_when_insufficient_data(db: Session) -> None:
    _populate_games(db, 5, _date(2024, 1, 1))
    with pytest.raises(ValueError, match="Insufficient"):
        train(db, _dt(2024, 2, 1), min_samples=50)


# ─── predict_game / store_prediction tests ───────────────────────────────────


def test_predict_game_returns_valid_probability(db: Session, trained_model: MoneylineModel) -> None:
    game = _add_upcoming(db, _date(2024, 5, 5), "BOS", "LAL")
    prob = predict_game(db, game, trained_model, {}, _dt(2024, 5, 5))
    assert 0.0 <= prob <= 1.0


def test_store_prediction_persists_row(db: Session) -> None:
    game = _add_upcoming(db, _date(2024, 5, 5), "BOS", "LAL")
    pred = store_prediction(db, game, 0.62, _dt(2024, 5, 5, 10))
    db.commit()

    assert isinstance(pred, ModelPrediction)
    assert pred.model_p == pytest.approx(0.62)
    assert pred.game_id == game.id


# ─── walk_forward_cv tests ────────────────────────────────────────────────────


def test_walk_forward_cv_returns_folds(db: Session) -> None:
    _populate_games(db, 80, _date(2024, 1, 1))
    cutoffs = [_dt(2024, 2, 1), _dt(2024, 3, 1)]
    folds = walk_forward_cv(db, cutoffs, test_days=20, min_samples=10, cv=2, n_estimators=5)
    assert len(folds) == 2
    assert all(isinstance(f, CVFold) for f in folds)


def test_walk_forward_cv_skips_cutoff_with_insufficient_data(db: Session) -> None:
    _populate_games(db, 30, _date(2024, 1, 1))
    folds = walk_forward_cv(db, [_dt(2024, 1, 5)], min_samples=50)
    assert folds == []
