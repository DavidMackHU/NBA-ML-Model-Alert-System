import datetime
from unittest.mock import MagicMock

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
from src.scripts.clv_report import main as clv_main

NOW = datetime.datetime(2024, 3, 1, 12)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def _make_factory(db: Session) -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory


def _seed_bet(
    session: Session,
    outcome: str,
    clv: float,
    ev_pct: float,
    alert_time: datetime.datetime | None = None,
    market: str = "h2h",
) -> None:
    t = alert_time or datetime.datetime(2024, 2, 20, 10)
    game = Game(
        game_id=f"g_{id(t)}_{outcome}_{clv}_{market}",
        date=t.date(),
        home_team="Boston Celtics",
        away_team="Los Angeles Lakers",
        tipoff_utc=t.replace(hour=23),
        status="final",
        home_score=110,
        away_score=100,
        fetched_at=t,
        as_of=t,
    )
    session.add(game)
    session.flush()

    alert = Alert(
        game_id=game.id,
        market=market,
        selection="Boston Celtics",
        dk_price=-110,
        dk_implied_p=0.48,
        pin_price=-130,
        pin_implied_p=0.56,
        model_p=0.60,
        ev_pct=ev_pct,
        edge_pin_vs_dk=0.08,
        alert_time=t,
        time_to_tip_seconds=10800,
        status="settled",
        as_of=t,
    )
    session.add(alert)
    session.flush()

    bet = BetsLog(
        alert_id=alert.id,
        outcome=outcome,
        pin_closing_price=-130,
        pin_closing_implied_p=0.48 + clv,
        clv=clv,
        settled_at=t.replace(hour=22),
        as_of=t.replace(hour=22),
    )
    session.add(bet)
    session.flush()


def test_clv_report_empty_db_runs(db: Session, capsys: pytest.CaptureFixture) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.scripts.clv_report.get_session_factory", lambda: _make_factory(db))
        clv_main(days=30, now=NOW)

    out = capsys.readouterr().out
    assert "CLV report" in out
    assert "30 days" in out


def test_clv_report_with_data(db: Session, capsys: pytest.CaptureFixture) -> None:
    _seed_bet(db, "win", 0.05, 0.08)
    _seed_bet(db, "loss", -0.01, 0.06)
    db.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.scripts.clv_report.get_session_factory", lambda: _make_factory(db))
        clv_main(days=30, now=NOW)

    out = capsys.readouterr().out
    assert "Rolling CLV Summary" in out
    assert "By Market" in out
    assert "h2h" in out
    # mean CLV = (0.05 + -0.01) / 2 = +0.020
    assert "+0.020" in out


def test_clv_report_market_breakdown(db: Session, capsys: pytest.CaptureFixture) -> None:
    _seed_bet(db, "win", 0.05, 0.08, market="h2h")
    _seed_bet(db, "loss", 0.02, 0.06, market="player_points")
    db.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.scripts.clv_report.get_session_factory", lambda: _make_factory(db))
        clv_main(days=30, now=NOW)

    out = capsys.readouterr().out
    assert "h2h" in out
    assert "player_points" in out


def test_clv_report_small_sample_note(db: Session, capsys: pytest.CaptureFixture) -> None:
    _seed_bet(db, "win", 0.04, 0.07)
    db.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.scripts.clv_report.get_session_factory", lambda: _make_factory(db))
        clv_main(days=30, now=NOW)

    out = capsys.readouterr().out
    assert "Sample size is small" in out


def test_clv_report_excludes_old_bets(db: Session, capsys: pytest.CaptureFixture) -> None:
    # Bet within the window
    _seed_bet(db, "win", 0.05, 0.08, alert_time=datetime.datetime(2024, 2, 20))
    # Bet older than 30 days before NOW (2024-03-01 − 30d = 2024-01-31)
    _seed_bet(db, "win", 0.10, 0.12, alert_time=datetime.datetime(2024, 1, 10))
    db.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("src.scripts.clv_report.get_session_factory", lambda: _make_factory(db))
        clv_main(days=30, now=NOW)

    out = capsys.readouterr().out
    # Only 1 bet in window, so small-sample note fires
    assert "Sample size is small" in out
    assert "(1 settled bets)" in out
