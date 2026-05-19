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
from src.db.models import Game, ModelPrediction, OddsSnapshot
from src.backtest.engine import (
    BacktestBet,
    Scenario,
    aggregate,
    apply_scenario,
    clv_of,
    pnl_flat,
    run_backtest,
)


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
    game_id: str = "g1",
    home: str = "Boston Celtics",
    away: str = "Los Angeles Lakers",
    home_score: int | None = 110,
    away_score: int | None = 100,
    status: str = "final",
    tipoff_hour: int = 20,
) -> Game:
    g = Game(
        game_id=game_id,
        date=datetime.date(2024, 1, 15),
        home_team=home,
        away_team=away,
        tipoff_utc=_dt(2024, 1, 15, tipoff_hour),
        status=status,
        home_score=home_score,
        away_score=away_score,
        fetched_at=_dt(2024, 1, 15),
        as_of=_dt(2024, 1, 15),
    )
    session.add(g)
    session.flush()
    return g


def _add_odds(
    session: Session,
    game: Game,
    book: str,
    selection: str,
    price: int,
    fetched_at: datetime.datetime,
) -> None:
    session.add(
        OddsSnapshot(
            game_id=game.id,
            book=book,
            market="h2h",
            selection=selection,
            line=None,
            price=price,
            fetched_at=fetched_at,
            as_of=fetched_at,
        )
    )
    session.flush()


def _add_pred(
    session: Session,
    game: Game,
    selection: str,
    model_p: float,
    as_of: datetime.datetime,
) -> None:
    session.add(
        ModelPrediction(
            game_id=game.id,
            market="h2h",
            selection=selection,
            model_version="xgb_v1",
            model_p=model_p,
            fetched_at=as_of,
            as_of=as_of,
        )
    )
    session.flush()


def _make_bet(
    outcome: int | None = 1,
    dk_price: int = -110,
    dk_fair_p: float = 0.48,
    pin_fair_p: float = 0.53,
    pin_closing_fair_p: float = 0.55,
    model_p: float = 0.60,
    ev_pct: float = 0.25,
) -> BacktestBet:
    return BacktestBet(
        game_id=1,
        market="h2h",
        selection="Boston Celtics",
        dk_price=dk_price,
        dk_fair_p=dk_fair_p,
        pin_fair_p=pin_fair_p,
        pin_closing_fair_p=pin_closing_fair_p,
        model_p=model_p,
        ev_pct=ev_pct,
        outcome=outcome,
        game_date=datetime.date(2024, 1, 15),
    )


# ─── clv_of tests ─────────────────────────────────────────────────────────────


def test_clv_of_positive_when_beat_close() -> None:
    assert clv_of(0.48, 0.55) == pytest.approx(0.07, rel=1e-9)


def test_clv_of_zero_when_equal() -> None:
    assert clv_of(0.50, 0.50) == pytest.approx(0.0, abs=1e-12)


def test_clv_of_negative_when_lagged_close() -> None:
    assert clv_of(0.55, 0.48) == pytest.approx(-0.07, rel=1e-9)


# ─── pnl_flat tests ───────────────────────────────────────────────────────────


def test_pnl_flat_positive_odds_win() -> None:
    assert pnl_flat(110, 1) == pytest.approx(1.10, rel=1e-9)


def test_pnl_flat_negative_odds_win() -> None:
    assert pnl_flat(-110, 1) == pytest.approx(100.0 / 110.0, rel=1e-9)


def test_pnl_flat_loss_is_minus_one() -> None:
    assert pnl_flat(-110, 0) == pytest.approx(-1.0)
    assert pnl_flat(200, 0) == pytest.approx(-1.0)


# ─── aggregate tests ──────────────────────────────────────────────────────────


def test_aggregate_empty_list_returns_zeros() -> None:
    r = aggregate([])
    assert r.n_bets == 0
    assert r.n_settled == 0
    assert r.mean_clv == 0.0


def test_aggregate_all_unsettled_returns_zeros() -> None:
    bets = [_make_bet(outcome=None), _make_bet(outcome=None)]
    r = aggregate(bets)
    assert r.n_bets == 2
    assert r.n_settled == 0
    assert r.roi == 0.0


def test_aggregate_mean_clv_computed() -> None:
    # bet1: clv=0.55-0.48=0.07; bet2: clv=0.50-0.50=0.00
    b1 = _make_bet(outcome=1, dk_fair_p=0.48, pin_closing_fair_p=0.55)
    b2 = _make_bet(outcome=0, dk_fair_p=0.50, pin_closing_fair_p=0.50)
    r = aggregate([b1, b2])
    assert r.mean_clv == pytest.approx((0.07 + 0.0) / 2, rel=1e-9)


def test_aggregate_roi_computed() -> None:
    # -110 win: pnl = 100/110; -110 loss: pnl = -1
    b_win = _make_bet(outcome=1, dk_price=-110)
    b_loss = _make_bet(outcome=0, dk_price=-110)
    r = aggregate([b_win, b_loss])
    expected_roi = (100.0 / 110.0 + (-1.0)) / 2
    assert r.roi == pytest.approx(expected_roi, rel=1e-9)


def test_aggregate_brier_score_computed() -> None:
    # model_p=0.6, outcome=1 → (0.6-1)^2=0.16; outcome=0 → (0.6-0)^2=0.36
    b1 = _make_bet(outcome=1, model_p=0.6)
    b2 = _make_bet(outcome=0, model_p=0.6)
    r = aggregate([b1, b2])
    assert r.brier_score == pytest.approx((0.16 + 0.36) / 2, rel=1e-9)


# ─── apply_scenario tests ─────────────────────────────────────────────────────


def test_apply_scenario_perfect_unchanged() -> None:
    bets = [_make_bet(), _make_bet()]
    result = apply_scenario(bets, Scenario.PERFECT)
    assert len(result) == 2
    assert result[0].dk_fair_p == pytest.approx(bets[0].dk_fair_p)


def test_apply_scenario_tick_worse_increases_dk_fair_p() -> None:
    bet = _make_bet(dk_fair_p=0.48)
    result = apply_scenario([bet], Scenario.TICK_WORSE)
    assert result[0].dk_fair_p == pytest.approx(0.485, rel=1e-9)


def test_apply_scenario_unavailable_20pct_drops_every_5th() -> None:
    bets = [_make_bet() for _ in range(10)]
    result = apply_scenario(bets, Scenario.UNAVAILABLE_20PCT)
    assert len(result) == 8  # indices 0-9, drop 0 and 5


def test_apply_scenario_limit_after_200_keeps_first_200() -> None:
    bets = [_make_bet() for _ in range(250)]
    result = apply_scenario(bets, Scenario.LIMIT_AFTER_200)
    assert len(result) == 200


# ─── run_backtest integration tests ───────────────────────────────────────────


def _setup_game_with_edge(session: Session) -> Game:
    """Add a game with DK + Pin odds and a model prediction that fires an edge."""
    game = _add_game(session)
    tipoff = _dt(2024, 1, 15, 20)
    as_of = _dt(2024, 1, 15, 18)  # 2h before tipoff — alert time

    # DK odds: Boston -110 (fair ~0.48), LA -110 (fair ~0.52)
    _add_odds(session, game, "draftkings", "Boston Celtics", -110, as_of)
    _add_odds(session, game, "draftkings", "Los Angeles Lakers", -110, as_of)

    # Pinnacle pre-game: Boston -130 (fair ~0.55) — agrees with model direction
    _add_odds(session, game, "pinnacle", "Boston Celtics", -130, as_of)
    _add_odds(session, game, "pinnacle", "Los Angeles Lakers", 110, as_of)

    # Pinnacle closing: Boston -140 (moves further in model direction)
    _add_odds(session, game, "pinnacle", "Boston Celtics", -140, tipoff)
    _add_odds(session, game, "pinnacle", "Los Angeles Lakers", 120, tipoff)

    # Model prediction well above DK fair → edge fires
    _add_pred(session, game, "Boston Celtics", 0.65, as_of)
    _add_pred(session, game, "Los Angeles Lakers", 0.35, as_of)

    session.commit()
    return game


def test_run_backtest_returns_all_four_scenarios(db: Session) -> None:
    _setup_game_with_edge(db)
    results = run_backtest(db, datetime.date(2024, 1, 1), datetime.date(2024, 2, 1))
    assert set(results.keys()) == set(Scenario)


def test_run_backtest_no_games_returns_empty_results(db: Session) -> None:
    results = run_backtest(db, datetime.date(2024, 1, 1), datetime.date(2024, 2, 1))
    for r in results.values():
        assert r.n_bets == 0


def test_run_backtest_threshold_filters_weak_edges(db: Session) -> None:
    _setup_game_with_edge(db)
    # Very high threshold — the edge should not fire
    results = run_backtest(
        db,
        datetime.date(2024, 1, 1),
        datetime.date(2024, 2, 1),
        ev_threshold=0.99,
    )
    for r in results.values():
        assert r.n_bets == 0


def test_run_backtest_outcome_maps_to_winner(db: Session) -> None:
    _setup_game_with_edge(db)  # Boston wins 110-100
    results = run_backtest(db, datetime.date(2024, 1, 1), datetime.date(2024, 2, 1))
    perfect = results[Scenario.PERFECT]
    # Boston Celtics edge fired and they won → hit_rate should be 1.0
    assert perfect.n_settled >= 1
    assert perfect.hit_rate == pytest.approx(1.0)
