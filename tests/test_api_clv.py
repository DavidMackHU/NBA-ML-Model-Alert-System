import datetime
import uuid

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import src.db.models  # noqa: F401


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_: BigInteger, compiler: object, **kw: object) -> str:
    return "INTEGER"


from src.api.app import app
from src.api.deps import get_db
from src.db.base import Base
from src.db.models import Alert, BetsLog, Game


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


@pytest.fixture()
def client(engine):
    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


def _seed(session: Session) -> None:
    g = Game(
        game_id="g1",
        date=datetime.date.today(),
        home_team="Boston Celtics",
        away_team="Los Angeles Lakers",
        tipoff_utc=datetime.datetime.utcnow(),
        status="final",
        home_score=110,
        away_score=100,
        fetched_at=datetime.datetime.utcnow(),
        as_of=datetime.datetime.utcnow(),
    )
    session.add(g)
    session.flush()

    recent = datetime.datetime.utcnow() - datetime.timedelta(days=5)
    for outcome, clv in [("win", 0.05), ("loss", 0.02)]:
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
            alert_time=recent,
            time_to_tip_seconds=10800,
            status="settled",
            as_of=recent,
        )
        session.add(a)
        session.flush()
        session.add(
            BetsLog(
                alert_id=a.id,
                outcome=outcome,
                pin_closing_price=-130,
                pin_closing_implied_p=0.48 + clv,
                clv=clv,
                settled_at=recent,
                as_of=recent,
            )
        )
    session.commit()


# ─── /api/clv ─────────────────────────────────────────────────────────────────


def test_clv_empty_returns_zeros(client: TestClient) -> None:
    data = client.get("/api/clv").json()
    assert data["n_bets"] == 0
    assert data["mean_clv"] == 0.0
    assert data["roi"] == 0.0


def test_clv_returns_summary(client: TestClient, db: Session) -> None:
    _seed(db)
    data = client.get("/api/clv?days=30").json()
    assert data["n_bets"] == 2
    assert data["days"] == 30
    assert data["mean_clv"] > 0.0


def test_clv_custom_days_reflected_in_response(client: TestClient) -> None:
    data = client.get("/api/clv?days=90").json()
    assert data["days"] == 90


def test_clv_empty_has_empty_series_and_breakdown(client: TestClient) -> None:
    data = client.get("/api/clv").json()
    assert data["daily"] == []
    assert data["by_market"] == []


def test_clv_returns_daily_series(client: TestClient, db: Session) -> None:
    _seed(db)
    data = client.get("/api/clv?days=30").json()
    assert len(data["daily"]) > 0
    point = data["daily"][0]
    assert "date" in point
    assert "cumulative_clv" in point
    assert "cumulative_ev" in point
    assert point["cumulative_clv"] > 0.0


def test_clv_returns_market_breakdown(client: TestClient, db: Session) -> None:
    _seed(db)
    data = client.get("/api/clv?days=30").json()
    assert len(data["by_market"]) > 0
    row = data["by_market"][0]
    assert row["market"] == "h2h"
    assert row["n_bets"] == 2
    assert row["mean_clv"] > 0.0
