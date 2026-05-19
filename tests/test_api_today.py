import datetime
import uuid
import zoneinfo

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
from src.db.models import Alert, Game

_ET = zoneinfo.ZoneInfo("America/New_York")


# ── time helpers (computed at call-time so tests always hit today's window) ───


def _in_window() -> datetime.datetime:
    """7pm ET today as naive UTC — inside today's slate window."""
    now_et = datetime.datetime.now(_ET)
    t_et = datetime.datetime.combine(now_et.date(), datetime.time(19, 0)).replace(tzinfo=_ET)
    return t_et.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def _out_of_window() -> datetime.datetime:
    """Yesterday noon ET as naive UTC — before today's 6am ET window start."""
    now_et = datetime.datetime.now(_ET)
    t_et = datetime.datetime.combine(
        now_et.date() - datetime.timedelta(days=1), datetime.time(12, 0)
    ).replace(tzinfo=_ET)
    return t_et.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def _recent() -> datetime.datetime:
    """3 hours ago in naive UTC — within the 6h stale cutoff."""
    return datetime.datetime.utcnow() - datetime.timedelta(hours=3)


def _stale() -> datetime.datetime:
    """7 hours ago in naive UTC — outside the 6h stale cutoff."""
    return datetime.datetime.utcnow() - datetime.timedelta(hours=7)


# ── fixtures ──────────────────────────────────────────────────────────────────


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


# ── seed helpers ──────────────────────────────────────────────────────────────


def _add_game(
    session: Session,
    tipoff: datetime.datetime | None = None,
    status: str = "scheduled",
    gid: str | None = None,
) -> Game:
    t = tipoff or _in_window()
    g = Game(
        game_id=gid or str(uuid.uuid4()),
        date=t.date(),
        home_team="Boston Celtics",
        away_team="Los Angeles Lakers",
        tipoff_utc=t,
        status=status,
        home_score=None,
        away_score=None,
        fetched_at=datetime.datetime.utcnow(),
        as_of=datetime.datetime.utcnow(),
    )
    session.add(g)
    session.flush()
    return g


def _add_alert(
    session: Session,
    game: Game,
    ev_pct: float = 0.05,
    status: str = "active",
    alert_time: datetime.datetime | None = None,
    model_p: float = 0.60,
    dk_implied_p: float = 0.48,
    pin_implied_p: float = 0.55,
) -> Alert:
    t = alert_time or _recent()
    a = Alert(
        game_id=game.id,
        market="h2h",
        selection="Boston Celtics",
        dk_price=-150,
        dk_implied_p=dk_implied_p,
        pin_price=-145,
        pin_implied_p=pin_implied_p,
        model_p=model_p,
        ev_pct=ev_pct,
        edge_pin_vs_dk=pin_implied_p - dk_implied_p,
        alert_time=t,
        time_to_tip_seconds=3600,
        status=status,
        as_of=t,
    )
    session.add(a)
    session.flush()
    return a


# ── tests ─────────────────────────────────────────────────────────────────────


def test_today_returns_empty_slate_when_no_games(client: TestClient) -> None:
    r = client.get("/api/today")
    assert r.status_code == 200
    body = r.json()
    assert body["games"] == []


def test_today_returns_all_games_even_without_edges(client: TestClient, db: Session) -> None:
    for i in range(3):
        _add_game(db, gid=f"g{i}")
    db.commit()

    r = client.get("/api/today")
    assert r.status_code == 200
    body = r.json()
    assert len(body["games"]) == 3
    assert all(g["best_edge"] is None for g in body["games"])


def test_today_picks_highest_ev_per_game(client: TestClient, db: Session) -> None:
    game = _add_game(db)
    _add_alert(db, game, ev_pct=0.03)
    _add_alert(db, game, ev_pct=0.08)
    _add_alert(db, game, ev_pct=0.05)
    db.commit()

    r = client.get("/api/today")
    body = r.json()
    assert len(body["games"]) == 1
    assert body["games"][0]["best_edge"]["ev_pct"] == pytest.approx(0.08)


def test_today_excludes_stale_alerts(client: TestClient, db: Session) -> None:
    game = _add_game(db)
    _add_alert(db, game, ev_pct=0.06, alert_time=_stale())
    db.commit()

    r = client.get("/api/today")
    body = r.json()
    assert len(body["games"]) == 1
    assert body["games"][0]["best_edge"] is None


def test_today_excludes_alerts_failing_pin_sanity(client: TestClient, db: Session) -> None:
    game = _add_game(db)
    # model says bet home (model_p > dk_implied_p) but Pin says fade (pin < dk)
    _add_alert(db, game, model_p=0.60, dk_implied_p=0.48, pin_implied_p=0.45)
    db.commit()

    r = client.get("/api/today")
    body = r.json()
    assert body["games"][0]["best_edge"] is None


def test_today_excludes_settled_alerts(client: TestClient, db: Session) -> None:
    game = _add_game(db)
    _add_alert(db, game, ev_pct=0.07, status="settled")
    db.commit()

    r = client.get("/api/today")
    body = r.json()
    assert body["games"][0]["best_edge"] is None


def test_today_excludes_games_outside_slate_window(client: TestClient, db: Session) -> None:
    _add_game(db, tipoff=_in_window(), gid="today")
    _add_game(db, tipoff=_out_of_window(), gid="yesterday")
    db.commit()

    r = client.get("/api/today")
    body = r.json()
    assert len(body["games"]) == 1


def test_today_best_edge_is_per_game_not_global(client: TestClient, db: Session) -> None:
    now_et = datetime.datetime.now(_ET)
    t1 = (
        datetime.datetime.combine(now_et.date(), datetime.time(19, 0))
        .replace(tzinfo=_ET)
        .astimezone(datetime.timezone.utc)
        .replace(tzinfo=None)
    )
    t2 = (
        datetime.datetime.combine(now_et.date(), datetime.time(21, 30))
        .replace(tzinfo=_ET)
        .astimezone(datetime.timezone.utc)
        .replace(tzinfo=None)
    )
    g1 = _add_game(db, tipoff=t1, gid="g1")
    g2 = _add_game(db, tipoff=t2, gid="g2")
    _add_alert(db, g1, ev_pct=0.04)
    _add_alert(db, g2, ev_pct=0.09)
    db.commit()

    r = client.get("/api/today")
    body = r.json()
    assert len(body["games"]) == 2
    assert all(g["best_edge"] is not None for g in body["games"])


def test_today_response_cache_header_present(client: TestClient) -> None:
    r = client.get("/api/today")
    assert "cache-control" in r.headers
    assert "max-age=30" in r.headers["cache-control"]


def test_today_games_sorted_by_tipoff(client: TestClient, db: Session) -> None:
    now_et = datetime.datetime.now(_ET)
    t_early = (
        datetime.datetime.combine(now_et.date(), datetime.time(19, 0))
        .replace(tzinfo=_ET)
        .astimezone(datetime.timezone.utc)
        .replace(tzinfo=None)
    )
    t_late = (
        datetime.datetime.combine(now_et.date(), datetime.time(22, 0))
        .replace(tzinfo=_ET)
        .astimezone(datetime.timezone.utc)
        .replace(tzinfo=None)
    )
    _add_game(db, tipoff=t_late, gid="late")
    _add_game(db, tipoff=t_early, gid="early")
    db.commit()

    r = client.get("/api/today")
    body = r.json()
    tipoffs = [g["tipoff_utc"] for g in body["games"]]
    assert tipoffs == sorted(tipoffs)
