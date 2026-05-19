import datetime
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_: BigInteger, compiler: object, **kw: object) -> str:
    return "INTEGER"


from src.api.app import app
from src.api.routes.stream import _event_generator
from src.db.base import Base
from src.db.models import Alert, Game


# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


def _seed(session: Session) -> Alert:
    g = Game(
        game_id="g1",
        date=datetime.date(2024, 1, 15),
        home_team="Boston Celtics",
        away_team="Los Angeles Lakers",
        tipoff_utc=datetime.datetime(2024, 1, 15, 23),
        status="scheduled",
        fetched_at=datetime.datetime(2024, 1, 15),
        as_of=datetime.datetime(2024, 1, 15),
    )
    session.add(g)
    session.flush()
    alert_time = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    a = Alert(
        id=uuid.uuid4(),
        game_id=g.id,
        market="h2h",
        selection="Boston Celtics",
        dk_price=-110,
        dk_implied_p=0.48,
        pin_price=-130,
        pin_implied_p=0.56,
        model_p=0.60,
        ev_pct=0.10,
        edge_pin_vs_dk=0.08,
        alert_time=alert_time,
        time_to_tip_seconds=10800,
        status="active",
        as_of=alert_time,
    )
    session.add(a)
    session.commit()
    return a


def _one_poll_request() -> MagicMock:
    """Mock request that disconnects after the first is_disconnected() check passes."""
    call_count = 0

    async def mock_disconnected() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 1  # False on first call, True on second (ends loop)

    req = MagicMock()
    req.is_disconnected = mock_disconnected
    return req


# ─── generator unit tests ─────────────────────────────────────────────────────


async def test_generator_emits_alert_event(engine, monkeypatch) -> None:
    with Session(engine) as session:
        _seed(session)

    monkeypatch.setattr("src.api.routes.stream.asyncio.sleep", AsyncMock())

    with Session(engine) as session:
        events = [e async for e in _event_generator(_one_poll_request(), session)]

    assert len(events) == 1
    assert events[0].event == "alert"


async def test_generator_event_payload_has_alert_fields(engine, monkeypatch) -> None:
    with Session(engine) as session:
        _seed(session)

    monkeypatch.setattr("src.api.routes.stream.asyncio.sleep", AsyncMock())

    with Session(engine) as session:
        events = [e async for e in _event_generator(_one_poll_request(), session)]

    payload = json.loads(events[0].data)
    assert payload["selection"] == "Boston Celtics"
    assert payload["home_team"] == "Boston Celtics"
    assert payload["ev_pct"] == pytest.approx(0.10, rel=1e-6)


async def test_generator_no_event_when_db_empty(engine, monkeypatch) -> None:
    monkeypatch.setattr("src.api.routes.stream.asyncio.sleep", AsyncMock())

    with Session(engine) as session:
        events = [e async for e in _event_generator(_one_poll_request(), session)]

    assert events == []


def test_sse_route_registered() -> None:
    paths = [r.path for r in app.routes]  # type: ignore[attr-defined]
    assert "/api/stream/alerts" in paths
