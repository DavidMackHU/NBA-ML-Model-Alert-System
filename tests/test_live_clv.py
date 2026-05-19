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
from src.db.models import Alert, BetsLog, Game
from src.tracker.live_clv import live_clv_series, live_clv_summary


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
        status="final",
        home_score=110,
        away_score=100,
        fetched_at=_dt(2024, 1, 15),
        as_of=_dt(2024, 1, 15),
    )
    session.add(g)
    session.flush()
    return g


def _add_alert_with_bet(
    session: Session,
    game: Game,
    alert_time: datetime.datetime,
    outcome: str,
    clv: float,
    dk_price: int = -110,
    ev_pct: float = 0.10,
) -> tuple[Alert, BetsLog]:
    alert = Alert(
        game_id=game.id,
        market="h2h",
        selection="Boston Celtics",
        dk_price=dk_price,
        dk_implied_p=0.48,
        pin_price=-130,
        pin_implied_p=0.56,
        model_p=0.60,
        ev_pct=ev_pct,
        edge_pin_vs_dk=0.08,
        alert_time=alert_time,
        time_to_tip_seconds=10800,
        status="settled",
        as_of=alert_time,
    )
    session.add(alert)
    session.flush()

    bet = BetsLog(
        alert_id=alert.id,
        outcome=outcome,
        pin_closing_price=-130,
        pin_closing_implied_p=0.48 + clv,
        clv=clv,
        settled_at=alert_time,
        as_of=alert_time,
    )
    session.add(bet)
    session.flush()
    return alert, bet


# ─── live_clv_summary tests ───────────────────────────────────────────────────


def test_live_clv_empty_returns_zeros(db: Session) -> None:
    result = live_clv_summary(db, days=30, now=_dt(2024, 2, 1))
    assert result.n_bets == 0
    assert result.n_settled == 0
    assert result.mean_clv == 0.0
    assert result.roi == 0.0


def test_live_clv_counts_bets_and_settled(db: Session) -> None:
    game = _add_game(db)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "win", 0.05)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "loss", -0.02)
    result = live_clv_summary(db, days=30, now=_dt(2024, 2, 1))
    assert result.n_bets == 2
    assert result.n_settled == 2


def test_live_clv_mean_clv_computed(db: Session) -> None:
    game = _add_game(db)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "win", 0.06)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "loss", 0.02)
    result = live_clv_summary(db, days=30, now=_dt(2024, 2, 1))
    assert result.mean_clv == pytest.approx(0.04, rel=1e-9)


def test_live_clv_win_rate_computed(db: Session) -> None:
    game = _add_game(db)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "win", 0.05)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "win", 0.05)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "loss", 0.05)
    result = live_clv_summary(db, days=30, now=_dt(2024, 2, 1))
    assert result.win_rate == pytest.approx(2 / 3, rel=1e-9)


def test_live_clv_roi_uses_dk_price(db: Session) -> None:
    game = _add_game(db)
    # -110 win: pnl = 100/110; -110 loss: pnl = -1
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "win", 0.05, dk_price=-110)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "loss", 0.01, dk_price=-110)
    result = live_clv_summary(db, days=30, now=_dt(2024, 2, 1))
    expected_roi = (100.0 / 110.0 + (-1.0)) / 2
    assert result.roi == pytest.approx(expected_roi, rel=1e-9)


def test_live_clv_respects_days_window(db: Session) -> None:
    game = _add_game(db)
    _add_alert_with_bet(db, game, _dt(2024, 1, 20), "win", 0.05)  # within 30 days of Feb 1
    _add_alert_with_bet(db, game, _dt(2023, 1, 1), "win", 0.10)  # older than 30 days
    result = live_clv_summary(db, days=30, now=_dt(2024, 2, 1))
    assert result.n_bets == 1
    assert result.mean_clv == pytest.approx(0.05, rel=1e-9)


def test_live_clv_mean_ev_computed(db: Session) -> None:
    game = _add_game(db)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "win", 0.05, ev_pct=0.08)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "loss", 0.01, ev_pct=0.12)
    result = live_clv_summary(db, days=30, now=_dt(2024, 2, 1))
    assert result.mean_ev == pytest.approx(0.10, rel=1e-9)


# ─── live_clv_series tests ────────────────────────────────────────────────────


def test_live_clv_series_empty(db: Session) -> None:
    daily, breakdown = live_clv_series(db, days=30, now=_dt(2024, 2, 1))
    assert daily == []
    assert breakdown == []


def test_live_clv_series_daily_cumulative(db: Session) -> None:
    game = _add_game(db)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "win", 0.06, ev_pct=0.08)
    _add_alert_with_bet(db, game, _dt(2024, 1, 16), "loss", 0.02, ev_pct=0.12)
    daily, _ = live_clv_series(db, days=30, now=_dt(2024, 2, 1))
    assert len(daily) == 2
    assert daily[0].date == "2024-01-15"
    assert daily[0].cumulative_clv == pytest.approx(0.06)
    assert daily[1].date == "2024-01-16"
    assert daily[1].cumulative_clv == pytest.approx(0.04)  # mean(0.06, 0.02)
    assert daily[1].n_bets == 2


def test_live_clv_series_market_breakdown(db: Session) -> None:
    game = _add_game(db)
    _add_alert_with_bet(db, game, _dt(2024, 1, 15), "win", 0.05, ev_pct=0.08)
    _, breakdown = live_clv_series(db, days=30, now=_dt(2024, 2, 1))
    assert len(breakdown) == 1
    assert breakdown[0].market == "h2h"
    assert breakdown[0].n_bets == 1
    assert breakdown[0].n_settled == 1
    assert breakdown[0].mean_clv == pytest.approx(0.05)
