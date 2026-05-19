import datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

import src.db.models  # noqa: F401


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_: BigInteger, compiler: object, **kw: object) -> str:
    return "INTEGER"


from src.db.base import Base
from src.db.models import Alert, Game
from src.scheduler.slate import alert_already_fired, has_games_today, upcoming_game_ids


# ─── fixtures & helpers ───────────────────────────────────────────────────────


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def _dt(year: int, month: int, day: int, hour: int = 12) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour)


def _add_game(
    session: Session,
    date: datetime.date = datetime.date(2024, 1, 15),
    status: str = "scheduled",
) -> Game:
    g = Game(
        game_id=f"g_{date}_{status}_{id(session)}",
        date=date,
        home_team="Boston Celtics",
        away_team="Los Angeles Lakers",
        tipoff_utc=_dt(date.year, date.month, date.day, 23),
        status=status,
        fetched_at=_dt(2024, 1, 15),
        as_of=_dt(2024, 1, 15),
    )
    session.add(g)
    session.flush()
    return g


def _add_alert(session: Session, game: Game, status: str = "active") -> Alert:
    a = Alert(
        game_id=game.id,
        market="h2h",
        selection="Boston Celtics",
        dk_price=-110,
        dk_implied_p=0.52,
        pin_price=-130,
        pin_implied_p=0.56,
        model_p=0.65,
        ev_pct=0.15,
        edge_pin_vs_dk=0.04,
        alert_time=_dt(2024, 1, 15, 20),
        time_to_tip_seconds=10800,
        status=status,
        as_of=_dt(2024, 1, 15, 20),
    )
    session.add(a)
    session.flush()
    return a


# ─── has_games_today tests ────────────────────────────────────────────────────


def test_has_games_today_true_when_game_exists(db: Session) -> None:
    _add_game(db, date=datetime.date(2024, 1, 15))
    assert has_games_today(db, datetime.date(2024, 1, 15)) is True


def test_has_games_today_false_when_no_games(db: Session) -> None:
    assert has_games_today(db, datetime.date(2024, 1, 15)) is False


def test_has_games_today_false_when_game_on_different_date(db: Session) -> None:
    _add_game(db, date=datetime.date(2024, 1, 16))
    assert has_games_today(db, datetime.date(2024, 1, 15)) is False


# ─── upcoming_game_ids tests ──────────────────────────────────────────────────


def test_upcoming_game_ids_returns_scheduled_games(db: Session) -> None:
    game = _add_game(db, date=datetime.date(2024, 1, 15), status="scheduled")
    result = upcoming_game_ids(db, datetime.date(2024, 1, 15))
    assert game.id in result


def test_upcoming_game_ids_includes_in_progress(db: Session) -> None:
    game = _add_game(db, date=datetime.date(2024, 1, 15), status="in_progress")
    result = upcoming_game_ids(db, datetime.date(2024, 1, 15))
    assert game.id in result


def test_upcoming_game_ids_excludes_final(db: Session) -> None:
    game = _add_game(db, date=datetime.date(2024, 1, 15), status="final")
    result = upcoming_game_ids(db, datetime.date(2024, 1, 15))
    assert game.id not in result


def test_upcoming_game_ids_empty_when_no_games(db: Session) -> None:
    assert upcoming_game_ids(db, datetime.date(2024, 1, 15)) == []


# ─── alert_already_fired tests ────────────────────────────────────────────────


def test_alert_already_fired_true_when_active_alert_exists(db: Session) -> None:
    game = _add_game(db)
    _add_alert(db, game, status="active")
    assert alert_already_fired(db, game.id, "h2h", "Boston Celtics") is True


def test_alert_already_fired_false_when_no_alert(db: Session) -> None:
    game = _add_game(db)
    assert alert_already_fired(db, game.id, "h2h", "Boston Celtics") is False


def test_alert_already_fired_false_when_alert_is_settled(db: Session) -> None:
    game = _add_game(db)
    _add_alert(db, game, status="settled")
    assert alert_already_fired(db, game.id, "h2h", "Boston Celtics") is False
