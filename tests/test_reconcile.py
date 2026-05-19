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
from src.db.models import Alert, BetsLog, Game, OddsSnapshot
from src.tracker.reconcile import _h2h_outcome, reconcile_alerts


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


TIPOFF = _dt(2024, 1, 15, 23)


def _add_final_game(session: Session, home_score: int = 110, away_score: int = 100) -> Game:
    g = Game(
        game_id="g1",
        date=datetime.date(2024, 1, 15),
        home_team="Boston Celtics",
        away_team="Los Angeles Lakers",
        tipoff_utc=TIPOFF,
        status="final",
        home_score=home_score,
        away_score=away_score,
        fetched_at=_dt(2024, 1, 15),
        as_of=_dt(2024, 1, 15),
    )
    session.add(g)
    session.flush()
    return g


def _add_pin_closing(session: Session, game: Game, home_price: int, away_price: int) -> None:
    for selection, price in [(game.home_team, home_price), (game.away_team, away_price)]:
        session.add(
            OddsSnapshot(
                game_id=game.id,
                book="pinnacle",
                market="h2h",
                selection=selection,
                line=None,
                price=price,
                fetched_at=TIPOFF,
                as_of=TIPOFF,
            )
        )
    session.flush()


def _add_active_alert(
    session: Session,
    game: Game,
    selection: str = "Boston Celtics",
    dk_implied_p: float = 0.48,
) -> Alert:
    a = Alert(
        game_id=game.id,
        market="h2h",
        selection=selection,
        dk_price=-110,
        dk_implied_p=dk_implied_p,
        pin_price=-130,
        pin_implied_p=0.565,
        model_p=0.65,
        ev_pct=0.146,
        edge_pin_vs_dk=0.085,
        alert_time=_dt(2024, 1, 15, 20),
        time_to_tip_seconds=10800,
        status="active",
        as_of=_dt(2024, 1, 15, 20),
    )
    session.add(a)
    session.flush()
    return a


# ─── _h2h_outcome tests ───────────────────────────────────────────────────────


def test_h2h_outcome_win_for_home_team(db: Session) -> None:
    game = _add_final_game(db, home_score=110, away_score=100)
    assert _h2h_outcome(game, "Boston Celtics") == "win"


def test_h2h_outcome_loss_for_away_team(db: Session) -> None:
    game = _add_final_game(db, home_score=110, away_score=100)
    assert _h2h_outcome(game, "Los Angeles Lakers") == "loss"


def test_h2h_outcome_none_when_scores_missing(db: Session) -> None:
    game = _add_final_game(db)
    game.home_score = None
    assert _h2h_outcome(game, "Boston Celtics") is None


# ─── reconcile_alerts tests ───────────────────────────────────────────────────


def test_reconcile_settles_active_alert(db: Session) -> None:
    game = _add_final_game(db)
    _add_pin_closing(db, game, -110, -110)
    alert = _add_active_alert(db, game)
    reconcile_alerts(db, _dt(2024, 1, 16))
    db.refresh(alert)
    assert alert.status == "settled"


def test_reconcile_writes_bets_log(db: Session) -> None:
    game = _add_final_game(db)
    _add_pin_closing(db, game, -110, -110)
    alert = _add_active_alert(db, game, dk_implied_p=0.48)
    reconcile_alerts(db, _dt(2024, 1, 16))
    entry = db.query(BetsLog).filter_by(alert_id=alert.id).one()
    assert entry.outcome == "win"
    # Pin -110/-110 de-vigs to exactly 0.5 each; CLV = 0.5 - 0.48 = 0.02
    assert entry.clv == pytest.approx(0.02, abs=1e-4)


def test_reconcile_loss_outcome_correct(db: Session) -> None:
    game = _add_final_game(db, home_score=110, away_score=100)
    _add_pin_closing(db, game, -110, -110)
    alert = _add_active_alert(db, game, selection="Los Angeles Lakers")
    reconcile_alerts(db, _dt(2024, 1, 16))
    entry = db.query(BetsLog).filter_by(alert_id=alert.id).one()
    assert entry.outcome == "loss"


def test_reconcile_skips_non_final_games(db: Session) -> None:
    game = _add_final_game(db)
    game.status = "scheduled"
    db.flush()
    _add_active_alert(db, game)
    n = reconcile_alerts(db, _dt(2024, 1, 16))
    assert n == 0
    assert db.query(BetsLog).count() == 0


def test_reconcile_is_idempotent(db: Session) -> None:
    game = _add_final_game(db)
    _add_pin_closing(db, game, -110, -110)
    _add_active_alert(db, game)
    n1 = reconcile_alerts(db, _dt(2024, 1, 16))
    n2 = reconcile_alerts(db, _dt(2024, 1, 16))
    assert n1 == 1
    assert n2 == 0
    assert db.query(BetsLog).count() == 1


def test_reconcile_settles_without_pin_closing_when_outcome_known(db: Session) -> None:
    # No Pin closing odds added — CLV will be None but outcome should still record
    game = _add_final_game(db)
    alert = _add_active_alert(db, game)
    n = reconcile_alerts(db, _dt(2024, 1, 16))
    assert n == 1
    entry = db.query(BetsLog).filter_by(alert_id=alert.id).one()
    assert entry.outcome == "win"
    assert entry.clv is None
