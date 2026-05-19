import datetime
from unittest.mock import AsyncMock, patch

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
from src.edge.ev import EdgeResult
from src.alerts.telegram import _format_time_to_tip, fire_alert, format_message


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


def _add_game(session: Session) -> Game:
    g = Game(
        game_id="g1",
        date=datetime.date(2024, 1, 15),
        home_team="Boston Celtics",
        away_team="Los Angeles Lakers",
        tipoff_utc=_dt(2024, 1, 15, 23),
        status="scheduled",
        fetched_at=_dt(2024, 1, 15),
        as_of=_dt(2024, 1, 15),
    )
    session.add(g)
    session.flush()
    return g


def _make_edge(game_id: int) -> EdgeResult:
    return EdgeResult(
        game_id=game_id,
        market="h2h",
        selection="Boston Celtics",
        dk_price=-110,
        dk_fair_p=0.524,
        pin_price=-130,
        pin_fair_p=0.565,
        model_p=0.65,
        ev_pct=0.146,
        edge_pin_vs_dk=0.041,
    )


def _make_alert(game: Game, session: Session) -> Alert:
    a = Alert(
        game_id=game.id,
        market="h2h",
        selection="Boston Celtics",
        dk_price=-110,
        dk_implied_p=0.524,
        pin_price=-130,
        pin_implied_p=0.565,
        model_p=0.65,
        ev_pct=0.146,
        edge_pin_vs_dk=0.041,
        alert_time=_dt(2024, 1, 15, 20),
        time_to_tip_seconds=10800,
        status="active",
        as_of=_dt(2024, 1, 15, 20),
    )
    session.add(a)
    session.flush()
    return a


# ─── _format_time_to_tip tests ────────────────────────────────────────────────


def test_format_time_to_tip_hours_and_minutes() -> None:
    assert _format_time_to_tip(8100) == "2h 15m"


def test_format_time_to_tip_minutes_only() -> None:
    assert _format_time_to_tip(900) == "15m"


def test_format_time_to_tip_zero_or_negative() -> None:
    assert _format_time_to_tip(0) == "at/past tipoff"
    assert _format_time_to_tip(-60) == "at/past tipoff"


# ─── format_message tests ─────────────────────────────────────────────────────


def test_format_message_contains_game_matchup(db: Session) -> None:
    game = _add_game(db)
    alert = _make_alert(game, db)
    msg = format_message(game, alert)
    assert "Los Angeles Lakers" in msg
    assert "Boston Celtics" in msg
    assert "@" in msg


def test_format_message_contains_prices_and_probs(db: Session) -> None:
    game = _add_game(db)
    alert = _make_alert(game, db)
    msg = format_message(game, alert)
    assert "-110" in msg
    assert "-130" in msg
    assert "52.4%" in msg
    assert "56.5%" in msg
    assert "65.0%" in msg


def test_format_message_contains_ev_and_edge(db: Session) -> None:
    game = _add_game(db)
    alert = _make_alert(game, db)
    msg = format_message(game, alert)
    assert "14.6%" in msg  # ev_pct=0.146 → 14.6%
    assert "4.1pp" in msg  # edge_pin_vs_dk=0.041 → 4.1pp


def test_format_message_contains_alert_id(db: Session) -> None:
    game = _add_game(db)
    alert = _make_alert(game, db)
    msg = format_message(game, alert)
    assert str(alert.id) in msg


# ─── fire_alert tests ─────────────────────────────────────────────────────────


async def test_fire_alert_stores_alert_and_commits(db: Session) -> None:
    game = _add_game(db)
    edge = _make_edge(game.id)
    as_of = _dt(2024, 1, 15, 20)
    with patch("src.alerts.telegram.send_alert", new_callable=AsyncMock):
        alert = await fire_alert(db, game, edge, as_of, "token", "chat123")
    assert db.query(Alert).filter_by(id=alert.id).one().selection == "Boston Celtics"


async def test_fire_alert_send_called_with_formatted_message(db: Session) -> None:
    game = _add_game(db)
    edge = _make_edge(game.id)
    as_of = _dt(2024, 1, 15, 20)
    with patch("src.alerts.telegram.send_alert", new_callable=AsyncMock) as mock_send:
        await fire_alert(db, game, edge, as_of, "mytoken", "mychat")
    mock_send.assert_called_once()
    args, _ = mock_send.call_args
    assert args[0] == "mytoken"
    assert args[1] == "mychat"
    assert "Boston Celtics" in args[2]


async def test_fire_alert_propagates_send_failure(db: Session) -> None:
    game = _add_game(db)
    edge = _make_edge(game.id)
    as_of = _dt(2024, 1, 15, 20)
    with patch(
        "src.alerts.telegram.send_alert",
        new_callable=AsyncMock,
        side_effect=Exception("Telegram unavailable"),
    ):
        with pytest.raises(Exception, match="Telegram unavailable"):
            await fire_alert(db, game, edge, as_of, "token", "chat")
