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
from src.db.models import Game, ModelPrediction, Player, PlayerGameStats
from src.ingestion.nba_stats import NBA_TEAM_NAMES
from src.models.props import (
    FEATURE_COLS,
    PropsCVFold,
    PropsModel,
    build_training_dataset,
    predict_player,
    store_props_prediction,
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
) -> Game:
    g = Game(
        game_id=f"upc{game_date}{home_abbr}",
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


def _add_player(session: Session, pid: str, name: str, team_abbr: str) -> Player:
    p = Player(
        player_id=pid,
        name=name,
        team_abbreviation=team_abbr,
        position="F",
        is_active=True,
        as_of=_dt(2024, 1, 1),
    )
    session.add(p)
    session.flush()
    return p


def _add_player_stats(
    session: Session,
    game: Game,
    player: Player,
    points: int,
    minutes: float = 30.0,
    usage: float = 20.0,
) -> PlayerGameStats:
    pgs = PlayerGameStats(
        game_id=game.id,
        player_id=player.id,
        minutes=minutes,
        points=points,
        usage_pct=usage,
        fetched_at=_dt(game.date.year, game.date.month, game.date.day),
        as_of=_dt(game.date.year, game.date.month, game.date.day),
    )
    session.add(pgs)
    session.flush()
    return pgs


def _populate_player_games(
    session: Session,
    player: Player,
    n: int,
    start: datetime.date,
    team_abbr: str = "BOS",
    opp_abbr: str = "LAL",
) -> None:
    """Add n games for player; points cycle 10–24 to provide target variance."""
    for i in range(n):
        d = start + datetime.timedelta(days=i)
        # Alternate home/away so is_home feature is not constant
        if i % 2 == 0:
            game = _add_game(session, d, team_abbr, opp_abbr, 110, 100, gid=f"pp{i}")
        else:
            game = _add_game(session, d, opp_abbr, team_abbr, 100, 110, gid=f"pp{i}")
        _add_player_stats(session, game, player, points=10 + (i % 15))
    session.commit()


# ─── build_training_dataset tests ────────────────────────────────────────────


def test_build_training_dataset_correct_shape(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    _populate_player_games(db, player, 5, _date(2024, 1, 1))

    X, y = build_training_dataset(db, _dt(2024, 2, 1))
    assert X.shape == (5, len(FEATURE_COLS))
    assert len(y) == 5


def test_build_training_dataset_labels_match_points(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    game1 = _add_game(db, _date(2024, 1, 10), "BOS", "LAL", 110, 100, gid="g1")
    game2 = _add_game(db, _date(2024, 1, 11), "BOS", "LAL", 110, 100, gid="g2")
    _add_player_stats(db, game1, player, points=20)
    _add_player_stats(db, game2, player, points=35)
    db.commit()

    _, y = build_training_dataset(db, _dt(2024, 2, 1))
    assert list(y) == pytest.approx([20.0, 35.0])


def test_build_training_dataset_excludes_game_on_as_of_date(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    game = _add_game(db, _date(2024, 1, 15), "BOS", "LAL", 110, 100)
    _add_player_stats(db, game, player, points=22)
    db.commit()

    X, _ = build_training_dataset(db, _dt(2024, 1, 15))
    assert len(X) == 0


def test_build_training_dataset_excludes_dnp_rows(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    game = _add_game(db, _date(2024, 1, 10), "BOS", "LAL", 110, 100)
    _add_player_stats(db, game, player, points=0, minutes=0.0)
    db.commit()

    X, _ = build_training_dataset(db, _dt(2024, 2, 1))
    assert len(X) == 0


def test_build_training_dataset_excludes_missing_points(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    game = _add_game(db, _date(2024, 1, 10), "BOS", "LAL", 110, 100)
    pgs = PlayerGameStats(
        game_id=game.id,
        player_id=player.id,
        minutes=30.0,
        points=None,
        fetched_at=_dt(2024, 1, 10),
        as_of=_dt(2024, 1, 10),
    )
    db.add(pgs)
    db.commit()

    X, _ = build_training_dataset(db, _dt(2024, 2, 1))
    assert len(X) == 0


def test_build_training_dataset_rest_days_computed(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    game1 = _add_game(db, _date(2024, 1, 1), "BOS", "LAL", 110, 100, gid="r1")
    game2 = _add_game(db, _date(2024, 1, 4), "BOS", "LAL", 110, 100, gid="r2")
    _add_player_stats(db, game1, player, points=20)
    _add_player_stats(db, game2, player, points=25)
    db.commit()

    X, _ = build_training_dataset(db, _dt(2024, 2, 1))
    # game1: no prior → rest_days default=7; game2: 4-1=3 days rest
    assert X["rest_days"].iloc[0] == pytest.approx(7.0)
    assert X["rest_days"].iloc[1] == pytest.approx(3.0)


# ─── train tests ─────────────────────────────────────────────────────────────


@pytest.fixture()
def trained_model(db: Session) -> PropsModel:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    _populate_player_games(db, player, 30, _date(2024, 1, 1))
    return train(db, _dt(2024, 5, 1), min_samples=10, n_estimators=5)


def test_train_returns_props_model(trained_model: PropsModel) -> None:
    assert isinstance(trained_model, PropsModel)


def test_train_records_n_train(trained_model: PropsModel) -> None:
    assert trained_model.n_train == 30


def test_train_raises_when_insufficient_data(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    _populate_player_games(db, player, 5, _date(2024, 1, 1))
    with pytest.raises(ValueError, match="Insufficient"):
        train(db, _dt(2024, 2, 1), min_samples=50)


# ─── predict_player tests ─────────────────────────────────────────────────────


def test_predict_player_returns_correct_columns(db: Session, trained_model: PropsModel) -> None:
    game = _add_upcoming(db, _date(2024, 5, 5), "BOS", "LAL")
    player = db.query(Player).first()
    result = predict_player(db, player, game, trained_model, _dt(2024, 5, 5))
    assert set(result.columns) == {"p10", "p50", "p90"}
    assert len(result) == 1


def test_predict_player_values_are_finite(db: Session, trained_model: PropsModel) -> None:
    import math

    game = _add_upcoming(db, _date(2024, 5, 5), "BOS", "LAL")
    player = db.query(Player).first()
    result = predict_player(db, player, game, trained_model, _dt(2024, 5, 5))
    for col in ("p10", "p50", "p90"):
        assert math.isfinite(result[col].iloc[0])


# ─── store_props_prediction tests ─────────────────────────────────────────────


def test_store_props_prediction_persists_row(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    game = _add_upcoming(db, _date(2024, 5, 5), "BOS", "LAL")
    pred = store_props_prediction(db, game, player, 12.5, 22.0, 34.0, _dt(2024, 5, 5, 10))
    db.commit()

    assert isinstance(pred, ModelPrediction)
    assert pred.game_id == game.id
    assert pred.model_p == pytest.approx(22.0)
    assert pred.market == "player_points"
    assert pred.selection == "Star Player"


def test_store_props_prediction_features_json_has_band(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    game = _add_upcoming(db, _date(2024, 5, 5), "BOS", "LAL")
    pred = store_props_prediction(db, game, player, 12.5, 22.0, 34.0, _dt(2024, 5, 5, 10))
    db.commit()

    assert pred.features_json is not None
    assert pred.features_json["p10"] == pytest.approx(12.5)
    assert pred.features_json["p90"] == pytest.approx(34.0)


# ─── walk_forward_cv tests ────────────────────────────────────────────────────


def test_walk_forward_cv_returns_folds(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    _populate_player_games(db, player, 80, _date(2024, 1, 1))
    cutoffs = [_dt(2024, 2, 1), _dt(2024, 3, 1)]
    folds = walk_forward_cv(db, cutoffs, test_days=20, min_samples=10, n_estimators=5)
    assert len(folds) == 2
    assert all(isinstance(f, PropsCVFold) for f in folds)


def test_walk_forward_cv_coverage_in_range(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    _populate_player_games(db, player, 80, _date(2024, 1, 1))
    folds = walk_forward_cv(db, [_dt(2024, 2, 1)], test_days=20, min_samples=10, n_estimators=5)
    assert len(folds) == 1
    assert 0.0 <= folds[0].coverage_80 <= 1.0


def test_walk_forward_cv_skips_cutoff_with_insufficient_data(db: Session) -> None:
    player = _add_player(db, "p1", "Star Player", "BOS")
    db.flush()
    _populate_player_games(db, player, 10, _date(2024, 1, 1))
    folds = walk_forward_cv(db, [_dt(2024, 1, 5)], min_samples=50)
    assert folds == []
