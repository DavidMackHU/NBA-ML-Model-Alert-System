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


def _add_game(session: Session) -> Game:
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
    return g


def _add_alert(
    session: Session, game: Game, hours_ago: float = 1.0, status: str = "active"
) -> Alert:
    alert_time = datetime.datetime.utcnow() - datetime.timedelta(hours=hours_ago)
    a = Alert(
        id=uuid.uuid4(),
        game_id=game.id,
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
        status=status,
        as_of=alert_time,
    )
    session.add(a)
    session.commit()
    return a


# ─── /api/alerts/live ─────────────────────────────────────────────────────────


def test_live_alerts_empty(client: TestClient) -> None:
    resp = client.get("/api/alerts/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["alerts"] == []


def test_live_alerts_returns_active_within_window(client: TestClient, db: Session) -> None:
    game = _add_game(db)
    db.commit()
    _add_alert(db, game, hours_ago=1.0)
    data = client.get("/api/alerts/live").json()
    assert data["count"] == 1
    assert data["alerts"][0]["selection"] == "Boston Celtics"
    assert data["alerts"][0]["home_team"] == "Boston Celtics"


def test_live_alerts_excludes_old_alerts(client: TestClient, db: Session) -> None:
    game = _add_game(db)
    db.commit()
    _add_alert(db, game, hours_ago=8.0)  # outside 6h window
    assert client.get("/api/alerts/live").json()["count"] == 0


# ─── /api/alerts/{alert_id} ───────────────────────────────────────────────────


def test_get_alert_by_id(client: TestClient, db: Session) -> None:
    game = _add_game(db)
    db.commit()
    alert = _add_alert(db, game, hours_ago=1.0)
    resp = client.get(f"/api/alerts/{alert.id}")
    assert resp.status_code == 200
    assert resp.json()["market"] == "h2h"


def test_get_alert_not_found(client: TestClient) -> None:
    resp = client.get(f"/api/alerts/{uuid.uuid4()}")
    assert resp.status_code == 404


# ─── AlertDetail — inspector fields ───────────────────────────────────────────


def test_alert_detail_has_inspector_fields(client: TestClient, db: Session) -> None:
    game = _add_game(db)
    db.commit()
    alert = _add_alert(db, game, hours_ago=1.0)
    data = client.get(f"/api/alerts/{alert.id}").json()
    assert "narrative" in data
    assert isinstance(data["narrative"], str)
    assert len(data["narrative"]) > 0
    assert "shap_features" in data
    assert isinstance(data["shap_features"], list)
    assert "similar_bets" in data
    assert isinstance(data["similar_bets"], list)


def _add_bets_log(
    session: Session, alert: Alert, outcome: str = "won", clv: float = 0.05
) -> BetsLog:
    b = BetsLog(
        alert_id=alert.id,
        outcome=outcome,
        pin_closing_implied_p=0.58,
        clv=clv,
        settled_at=datetime.datetime.utcnow(),
        as_of=datetime.datetime.utcnow(),
    )
    session.add(b)
    session.commit()
    return b


def test_alert_detail_similar_bets_populated(client: TestClient, db: Session) -> None:
    game = _add_game(db)
    db.commit()
    target = _add_alert(db, game, hours_ago=1.0)

    # Add a second game for the similar alert to avoid unique-game constraints
    g2 = Game(
        game_id="g2",
        date=datetime.date(2024, 1, 10),
        home_team="Boston Celtics",
        away_team="Golden State Warriors",
        tipoff_utc=datetime.datetime(2024, 1, 10, 23),
        status="final",
        fetched_at=datetime.datetime(2024, 1, 10),
        as_of=datetime.datetime(2024, 1, 10),
    )
    db.add(g2)
    db.flush()
    similar = Alert(
        id=uuid.uuid4(),
        game_id=g2.id,
        market="h2h",
        selection="Boston Celtics",
        dk_price=-115,
        dk_implied_p=0.49,
        pin_price=-125,
        pin_implied_p=0.54,
        model_p=0.58,
        ev_pct=0.07,
        edge_pin_vs_dk=0.05,
        alert_time=datetime.datetime(2024, 1, 10, 20),
        time_to_tip_seconds=10800,
        status="settled",
        as_of=datetime.datetime(2024, 1, 10, 20),
    )
    db.add(similar)
    db.flush()
    _add_bets_log(db, similar)

    data = client.get(f"/api/alerts/{target.id}").json()
    assert len(data["similar_bets"]) == 1
    sb = data["similar_bets"][0]
    assert sb["outcome"] == "won"
    assert sb["market"] == "h2h"
