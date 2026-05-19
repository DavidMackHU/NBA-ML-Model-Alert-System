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
from src.db.models import Game, OddsSnapshot
from src.edge.devig import (
    MarketOdds,
    american_to_raw_prob,
    devig_power,
    latest_market_odds,
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


def _add_snapshot(
    session: Session,
    game: Game,
    book: str,
    market: str,
    selection: str,
    price: int,
    fetched_at: datetime.datetime,
) -> OddsSnapshot:
    snap = OddsSnapshot(
        game_id=game.id,
        book=book,
        market=market,
        selection=selection,
        line=None,
        price=price,
        fetched_at=fetched_at,
        as_of=fetched_at,
    )
    session.add(snap)
    session.flush()
    return snap


# ─── american_to_raw_prob tests ───────────────────────────────────────────────


def test_american_to_raw_prob_even_money() -> None:
    assert american_to_raw_prob(100) == pytest.approx(0.5)
    assert american_to_raw_prob(-100) == pytest.approx(0.5)


def test_american_to_raw_prob_positive_odds() -> None:
    # +200 → 100/300 = 0.3333
    assert american_to_raw_prob(200) == pytest.approx(1 / 3, rel=1e-6)


def test_american_to_raw_prob_negative_odds() -> None:
    # -200 → 200/300 = 0.6667
    assert american_to_raw_prob(-200) == pytest.approx(2 / 3, rel=1e-6)


def test_american_to_raw_prob_heavy_favourite() -> None:
    # -500 → 500/600 ≈ 0.8333
    assert american_to_raw_prob(-500) == pytest.approx(500 / 600, rel=1e-6)


def test_american_to_raw_prob_complement_for_fair_market() -> None:
    # +100 / -100 are exact complements (no vig) → should sum to 1.0
    assert american_to_raw_prob(100) + american_to_raw_prob(-100) == pytest.approx(1.0)


# ─── devig_power tests ────────────────────────────────────────────────────────


def test_devig_power_fair_probs_sum_to_one() -> None:
    # -110 / -110 (standard American vig, both sides)
    fair = devig_power([-110, -110])
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)


def test_devig_power_symmetric_market_gives_half_each() -> None:
    fair = devig_power([-110, -110])
    assert fair[0] == pytest.approx(0.5, abs=1e-6)
    assert fair[1] == pytest.approx(0.5, abs=1e-6)


def test_devig_power_favourite_gets_higher_fair_prob() -> None:
    # -150 favourite vs +130 underdog
    fair = devig_power([-150, 130])
    assert fair[0] > fair[1]


def test_devig_power_removes_overround() -> None:
    raw = [american_to_raw_prob(p) for p in [-110, -110]]
    assert sum(raw) > 1.0  # has overround
    fair = devig_power([-110, -110])
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)


def test_devig_power_no_overround_normalises() -> None:
    # +100 / +100 → raw sum = 1.0 exactly, no vig to remove
    fair = devig_power([100, 100])
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    assert fair[0] == pytest.approx(0.5, abs=1e-9)


def test_devig_power_three_way_market_sums_to_one() -> None:
    fair = devig_power([-120, -110, 200])
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)


def test_devig_power_preserves_order() -> None:
    # Favourite should remain first after devigging
    fair = devig_power([-200, 160])
    assert fair[0] > fair[1]


def test_devig_power_raises_on_empty_prices() -> None:
    with pytest.raises(ValueError):
        devig_power([])


# ─── latest_market_odds tests ─────────────────────────────────────────────────


def test_latest_market_odds_returns_two_market_odds(db: Session) -> None:
    game = _add_game(db)
    t1 = _dt(2024, 1, 15, 10)
    _add_snapshot(db, game, "draftkings", "h2h", "Boston Celtics", -150, t1)
    _add_snapshot(db, game, "draftkings", "h2h", "Los Angeles Lakers", 130, t1)
    db.commit()

    result = latest_market_odds(db, game.id, "draftkings", "h2h", _dt(2024, 1, 15, 20))
    assert len(result) == 2
    assert all(isinstance(m, MarketOdds) for m in result)


def test_latest_market_odds_fair_probs_sum_to_one(db: Session) -> None:
    game = _add_game(db)
    t1 = _dt(2024, 1, 15, 10)
    _add_snapshot(db, game, "draftkings", "h2h", "Boston Celtics", -150, t1)
    _add_snapshot(db, game, "draftkings", "h2h", "Los Angeles Lakers", 130, t1)
    db.commit()

    result = latest_market_odds(db, game.id, "draftkings", "h2h", _dt(2024, 1, 15, 20))
    assert sum(m.fair_prob for m in result) == pytest.approx(1.0, abs=1e-9)


def test_latest_market_odds_uses_most_recent_snapshot(db: Session) -> None:
    game = _add_game(db)
    # Two snapshots for home team: early -150, later line moves to -170
    t1 = _dt(2024, 1, 15, 8)
    t2 = _dt(2024, 1, 15, 12)
    _add_snapshot(db, game, "draftkings", "h2h", "Boston Celtics", -150, t1)
    _add_snapshot(db, game, "draftkings", "h2h", "Boston Celtics", -170, t2)
    _add_snapshot(db, game, "draftkings", "h2h", "Los Angeles Lakers", 130, t1)
    db.commit()

    result = latest_market_odds(db, game.id, "draftkings", "h2h", _dt(2024, 1, 15, 20))
    home_odds = next(m for m in result if m.selection == "Boston Celtics")
    assert home_odds.price == -170


def test_latest_market_odds_respects_as_of_cutoff(db: Session) -> None:
    game = _add_game(db)
    t1 = _dt(2024, 1, 15, 20)  # after our query as_of
    _add_snapshot(db, game, "draftkings", "h2h", "Boston Celtics", -150, t1)
    _add_snapshot(db, game, "draftkings", "h2h", "Los Angeles Lakers", 130, t1)
    db.commit()

    result = latest_market_odds(db, game.id, "draftkings", "h2h", _dt(2024, 1, 15, 10))
    assert result == []


def test_latest_market_odds_empty_when_only_one_side(db: Session) -> None:
    game = _add_game(db)
    t1 = _dt(2024, 1, 15, 10)
    _add_snapshot(db, game, "draftkings", "h2h", "Boston Celtics", -150, t1)
    db.commit()

    result = latest_market_odds(db, game.id, "draftkings", "h2h", _dt(2024, 1, 15, 20))
    assert result == []


def test_latest_market_odds_raw_prob_equals_american_conversion(db: Session) -> None:
    game = _add_game(db)
    t1 = _dt(2024, 1, 15, 10)
    _add_snapshot(db, game, "pinnacle", "h2h", "Boston Celtics", -145, t1)
    _add_snapshot(db, game, "pinnacle", "h2h", "Los Angeles Lakers", 125, t1)
    db.commit()

    result = latest_market_odds(db, game.id, "pinnacle", "h2h", _dt(2024, 1, 15, 20))
    for m in result:
        assert m.raw_prob == pytest.approx(american_to_raw_prob(m.price), rel=1e-9)


def test_latest_market_odds_isolates_by_book(db: Session) -> None:
    game = _add_game(db)
    t1 = _dt(2024, 1, 15, 10)
    _add_snapshot(db, game, "draftkings", "h2h", "Boston Celtics", -150, t1)
    _add_snapshot(db, game, "draftkings", "h2h", "Los Angeles Lakers", 130, t1)
    _add_snapshot(db, game, "pinnacle", "h2h", "Boston Celtics", -145, t1)
    _add_snapshot(db, game, "pinnacle", "h2h", "Los Angeles Lakers", 125, t1)
    db.commit()

    dk = latest_market_odds(db, game.id, "draftkings", "h2h", _dt(2024, 1, 15, 20))
    pin = latest_market_odds(db, game.id, "pinnacle", "h2h", _dt(2024, 1, 15, 20))

    dk_home = next(m for m in dk if m.selection == "Boston Celtics")
    pin_home = next(m for m in pin if m.selection == "Boston Celtics")
    assert dk_home.price == -150
    assert pin_home.price == -145
