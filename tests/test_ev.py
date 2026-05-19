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
from src.edge.devig import MarketOdds
from src.edge.ev import EdgeResult, _ev, compute_edges, store_alert


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


def _mo(
    selection: str,
    price: int,
    fair_prob: float,
    book: str = "draftkings",
) -> MarketOdds:
    """Build a MarketOdds with raw_prob derived from fair_prob for simplicity."""
    return MarketOdds(
        selection=selection,
        book=book,
        price=price,
        raw_prob=fair_prob,  # not important for ev.py logic; fair_prob is what matters
        fair_prob=fair_prob,
    )


def _edge(game_id: int = 1) -> EdgeResult:
    return EdgeResult(
        game_id=game_id,
        market="h2h",
        selection="Boston Celtics",
        dk_price=-110,
        dk_fair_p=0.48,
        pin_price=-120,
        pin_fair_p=0.53,
        model_p=0.60,
        ev_pct=0.60 / 0.48 - 1.0,
        edge_pin_vs_dk=0.05,
    )


# ─── _ev tests ────────────────────────────────────────────────────────────────


def test_ev_positive_when_model_above_fair() -> None:
    assert _ev(0.55, 0.50) == pytest.approx(0.10, rel=1e-9)


def test_ev_zero_when_equal() -> None:
    assert _ev(0.50, 0.50) == pytest.approx(0.0, abs=1e-12)


def test_ev_negative_when_model_below_fair() -> None:
    assert _ev(0.45, 0.50) == pytest.approx(-0.10, rel=1e-9)


def test_ev_formula_matches_direct_calculation() -> None:
    model_p, dk_fair_p = 0.60, 0.55
    assert _ev(model_p, dk_fair_p) == pytest.approx(model_p / dk_fair_p - 1.0, rel=1e-9)


# ─── compute_edges tests ──────────────────────────────────────────────────────


def test_compute_edges_returns_edge_when_all_conditions_met() -> None:
    # model EV = 0.55/0.48 - 1 ≈ 0.146 > 0.03; pin_fair(0.53) > dk_fair(0.48) → agrees
    dk = [_mo("Boston", -110, 0.48), _mo("Los Angeles", -110, 0.52)]
    pin = [_mo("Boston", -120, 0.53, "pinnacle"), _mo("Los Angeles", 110, 0.47, "pinnacle")]
    result = compute_edges(1, "h2h", dk, pin, {"Boston": 0.55}, ev_threshold=0.03)
    assert len(result) == 1
    assert result[0].selection == "Boston"


def test_compute_edges_ev_pct_formula_correct() -> None:
    dk = [_mo("Boston", -110, 0.48), _mo("Los Angeles", -110, 0.52)]
    pin = [_mo("Boston", -120, 0.53, "pinnacle"), _mo("Los Angeles", 110, 0.47, "pinnacle")]
    result = compute_edges(1, "h2h", dk, pin, {"Boston": 0.56}, ev_threshold=0.03)
    assert result[0].ev_pct == pytest.approx(0.56 / 0.48 - 1.0, rel=1e-9)


def test_compute_edges_edge_pin_vs_dk_value_correct() -> None:
    dk = [_mo("Boston", -110, 0.48), _mo("Los Angeles", -110, 0.52)]
    pin = [_mo("Boston", -120, 0.55, "pinnacle"), _mo("Los Angeles", 100, 0.45, "pinnacle")]
    result = compute_edges(1, "h2h", dk, pin, {"Boston": 0.60}, ev_threshold=0.03)
    assert result[0].edge_pin_vs_dk == pytest.approx(0.55 - 0.48, rel=1e-9)


def test_compute_edges_below_threshold_excluded() -> None:
    # EV = 0.51/0.50 - 1 = 0.02 < 0.03 threshold
    dk = [_mo("Boston", -110, 0.50), _mo("Los Angeles", -110, 0.50)]
    pin = [_mo("Boston", -115, 0.51, "pinnacle"), _mo("Los Angeles", 105, 0.49, "pinnacle")]
    result = compute_edges(1, "h2h", dk, pin, {"Boston": 0.51}, ev_threshold=0.03)
    assert result == []


def test_compute_edges_pin_disagrees_excluded() -> None:
    # Model says Boston is underpriced (EV=0.20), but Pinnacle thinks Boston is overpriced
    dk = [_mo("Boston", -110, 0.50), _mo("Los Angeles", -110, 0.50)]
    pin = [_mo("Boston", 110, 0.45, "pinnacle"), _mo("Los Angeles", -130, 0.55, "pinnacle")]
    result = compute_edges(1, "h2h", dk, pin, {"Boston": 0.60}, ev_threshold=0.03)
    assert result == []


def test_compute_edges_missing_dk_selection_skipped() -> None:
    dk = [_mo("Los Angeles", -110, 0.50)]  # Boston absent
    pin = [_mo("Boston", -120, 0.53, "pinnacle"), _mo("Los Angeles", 110, 0.47, "pinnacle")]
    result = compute_edges(1, "h2h", dk, pin, {"Boston": 0.60})
    assert result == []


def test_compute_edges_missing_pin_selection_skipped() -> None:
    dk = [_mo("Boston", -110, 0.48), _mo("Los Angeles", -110, 0.52)]
    pin = [_mo("Los Angeles", 110, 0.47, "pinnacle")]  # Boston absent
    result = compute_edges(1, "h2h", dk, pin, {"Boston": 0.60})
    assert result == []


def test_compute_edges_empty_model_preds_returns_empty() -> None:
    dk = [_mo("Boston", -110, 0.48)]
    pin = [_mo("Boston", -115, 0.51, "pinnacle")]
    result = compute_edges(1, "h2h", dk, pin, {})
    assert result == []


def test_compute_edges_multiple_selections_partial_hit() -> None:
    # Boston passes; Los Angeles model is below dk_fair so EV < 0
    dk = [_mo("Boston", -110, 0.48), _mo("Los Angeles", -110, 0.52)]
    pin = [_mo("Boston", -120, 0.53, "pinnacle"), _mo("Los Angeles", -120, 0.53, "pinnacle")]
    preds = {"Boston": 0.60, "Los Angeles": 0.40}
    result = compute_edges(1, "h2h", dk, pin, preds, ev_threshold=0.03)
    assert len(result) == 1
    assert result[0].selection == "Boston"


# ─── store_alert tests ────────────────────────────────────────────────────────


def test_store_alert_persists_fields(db: Session) -> None:
    game = _add_game(db)
    edge = _edge(game.id)
    as_of = _dt(2024, 1, 15, 20)
    alert = store_alert(db, game, edge, as_of)
    db.commit()

    fetched = db.query(Alert).filter_by(id=alert.id).one()
    assert fetched.selection == "Boston Celtics"
    assert fetched.market == "h2h"
    assert fetched.dk_price == -110
    assert fetched.ev_pct == pytest.approx(edge.ev_pct, rel=1e-6)
    assert fetched.status == "active"


def test_store_alert_time_to_tip_seconds_correct(db: Session) -> None:
    game = _add_game(db)  # tipoff at 23:00
    edge = _edge(game.id)
    as_of = _dt(2024, 1, 15, 20)  # 3 hours before tipoff
    alert = store_alert(db, game, edge, as_of)
    assert alert.time_to_tip_seconds == 3 * 3600


def test_store_alert_clamps_to_zero_past_tipoff(db: Session) -> None:
    game = _add_game(db)  # tipoff at 23:00
    edge = _edge(game.id)
    as_of = _dt(2024, 1, 16, 1)  # 2 hours after tipoff
    alert = store_alert(db, game, edge, as_of)
    assert alert.time_to_tip_seconds == 0


def test_store_alert_prediction_id_defaults_none(db: Session) -> None:
    game = _add_game(db)
    edge = _edge(game.id)
    alert = store_alert(db, game, edge, _dt(2024, 1, 15, 20))
    assert alert.prediction_id is None
