import datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

import src.db.models  # noqa: F401 — registers all models with Base


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_: BigInteger, compiler: object, **kw: object) -> str:
    return "INTEGER"


from src.db.base import Base
from src.db.models import Game
from src.ingestion.nba_stats import NBA_TEAM_NAMES
from src.models.elo import (
    INITIAL_ELO,
    build_team_elos,
    expected_win_prob,
    home_win_prob,
    update_ratings,
)


# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def _dt(year: int, month: int, day: int, hour: int = 6) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour)


def _date(year: int, month: int, day: int) -> datetime.date:
    return datetime.date(year, month, day)


def _add_game(
    session: Session,
    game_date: datetime.date,
    home_abbr: str,
    away_abbr: str,
    home_score: int,
    away_score: int,
    gid: str | None = None,
) -> Game:
    g = Game(
        game_id=gid or f"{game_date}{home_abbr}{away_abbr}",
        date=game_date,
        home_team=NBA_TEAM_NAMES[home_abbr],
        away_team=NBA_TEAM_NAMES[away_abbr],
        tipoff_utc=_dt(game_date.year, game_date.month, game_date.day, 0),
        status="final",
        home_score=home_score,
        away_score=away_score,
        fetched_at=_dt(game_date.year, game_date.month, game_date.day),
        as_of=_dt(game_date.year, game_date.month, game_date.day),
    )
    session.add(g)
    session.flush()
    return g


# ─── pure function tests ──────────────────────────────────────────────────────


def test_expected_win_prob_equal_ratings() -> None:
    assert expected_win_prob(1500.0, 1500.0) == pytest.approx(0.5)


def test_expected_win_prob_higher_rated_favored() -> None:
    assert expected_win_prob(1600.0, 1500.0) > 0.5


def test_expected_win_prob_lower_rated_is_underdog() -> None:
    assert expected_win_prob(1400.0, 1500.0) < 0.5


def test_expected_win_prob_is_complement() -> None:
    p = expected_win_prob(1600.0, 1400.0)
    assert expected_win_prob(1400.0, 1600.0) == pytest.approx(1.0 - p)


def test_update_ratings_winner_increases_loser_drops() -> None:
    new_winner, new_loser = update_ratings(1500.0, 1500.0)
    assert new_winner > 1500.0
    assert new_loser < 1500.0


def test_update_ratings_elo_is_conserved() -> None:
    new_winner, new_loser = update_ratings(1500.0, 1500.0)
    assert new_winner + new_loser == pytest.approx(3000.0)


def test_update_ratings_upset_yields_larger_delta() -> None:
    # Underdog beating a favourite earns more Elo than an evenly matched win
    delta_upset = update_ratings(1400.0, 1600.0)[0] - 1400.0
    delta_even = update_ratings(1500.0, 1500.0)[0] - 1500.0
    assert delta_upset > delta_even


def test_home_win_prob_equal_elos_favors_home() -> None:
    elos = {"BOS": 1500.0, "LAL": 1500.0}
    assert home_win_prob("BOS", "LAL", elos) > 0.5


def test_home_win_prob_uses_initial_elo_for_missing_teams() -> None:
    # Home advantage must apply even when neither team has history
    assert home_win_prob("BOS", "LAL", {}) > 0.5


# ─── build_team_elos tests ────────────────────────────────────────────────────


def test_build_team_elos_empty_db_returns_empty(db: Session) -> None:
    assert build_team_elos(db, _dt(2024, 1, 15)) == {}


def test_build_team_elos_winner_gains_loser_drops(db: Session) -> None:
    _add_game(db, _date(2024, 1, 10), "BOS", "LAL", 110, 100)
    db.commit()

    elos = build_team_elos(db, _dt(2024, 1, 15))
    assert elos["BOS"] > INITIAL_ELO
    assert elos["LAL"] < INITIAL_ELO


def test_build_team_elos_away_winner_gains(db: Session) -> None:
    _add_game(db, _date(2024, 1, 10), "BOS", "LAL", 90, 100)  # LAL wins away
    db.commit()

    elos = build_team_elos(db, _dt(2024, 1, 15))
    assert elos["LAL"] > INITIAL_ELO
    assert elos["BOS"] < INITIAL_ELO


def test_build_team_elos_elo_sum_conserved(db: Session) -> None:
    _add_game(db, _date(2024, 1, 10), "BOS", "LAL", 110, 100)
    db.commit()

    elos = build_team_elos(db, _dt(2024, 1, 15))
    assert elos["BOS"] + elos["LAL"] == pytest.approx(INITIAL_ELO * 2)


def test_build_team_elos_excludes_game_on_as_of_date(db: Session) -> None:
    # date == as_of.date() must be excluded (strict less-than)
    _add_game(db, _date(2024, 1, 15), "BOS", "LAL", 110, 100)
    db.commit()

    assert build_team_elos(db, _dt(2024, 1, 15, 12)) == {}


def test_build_team_elos_excludes_non_final_games(db: Session) -> None:
    g = Game(
        game_id="sched01",
        date=_date(2024, 1, 10),
        home_team=NBA_TEAM_NAMES["BOS"],
        away_team=NBA_TEAM_NAMES["LAL"],
        tipoff_utc=_dt(2024, 1, 10, 0),
        status="scheduled",
        home_score=None,
        away_score=None,
        fetched_at=_dt(2024, 1, 10),
        as_of=_dt(2024, 1, 10),
    )
    db.add(g)
    db.commit()

    assert build_team_elos(db, _dt(2024, 1, 15)) == {}


def test_build_team_elos_multiple_games_compound(db: Session) -> None:
    _add_game(db, _date(2024, 1, 10), "BOS", "LAL", 110, 100, gid="g1")
    _add_game(db, _date(2024, 1, 12), "BOS", "MIA", 105, 95, gid="g2")
    db.commit()

    elos_after_one = build_team_elos(db, _dt(2024, 1, 11))  # only first game
    elos_after_two = build_team_elos(db, _dt(2024, 1, 15))  # both games
    assert elos_after_two["BOS"] > elos_after_one["BOS"]
