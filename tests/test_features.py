import datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

import src.db.models  # noqa: F401 — registers all models with Base


# SQLite uses BIGINT without ROWID aliasing, so autoincrement won't fire unless
# we render BigInteger as INTEGER for the SQLite dialect.
@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_: BigInteger, compiler: object, **kw: object) -> str:
    return "INTEGER"


from src.db.base import Base
from src.db.models import Game, Injury, OddsSnapshot, Player, PlayerGameStats, TeamGameStats
from src.features import odds_features, player_features, team_features
from src.features.builder import (
    GameFeatures,
    PlayerGameFeatures,
    build_game_features,
    build_player_features,
)
from src.features.team_features import ARENA_COORDS, arena_travel_km, haversine_km
from src.ingestion.nba_stats import NBA_TEAM_NAMES


# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def _dt(year: int, month: int, day: int, hour: int = 6, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute)


def _date(year: int, month: int, day: int) -> datetime.date:
    return datetime.date(year, month, day)


def _add_game(
    session: Session,
    game_date: datetime.date,
    home_abbr: str = "BOS",
    away_abbr: str = "LAL",
    gid: str | None = None,
) -> Game:
    g = Game(
        game_id=gid or f"{game_date}{home_abbr}{away_abbr}",
        date=game_date,
        home_team=NBA_TEAM_NAMES[home_abbr],
        away_team=NBA_TEAM_NAMES[away_abbr],
        tipoff_utc=_dt(game_date.year, game_date.month, game_date.day, 0),
        status="final",
        fetched_at=_dt(game_date.year, game_date.month, game_date.day),
        as_of=_dt(game_date.year, game_date.month, game_date.day),
    )
    session.add(g)
    session.flush()
    return g


def _add_team_stats(
    session: Session,
    game: Game,
    abbr: str,
    is_home: bool,
    pace: float = 100.0,
    ortg: float = 110.0,
    drtg: float = 108.0,
    as_of: datetime.datetime | None = None,
) -> TeamGameStats:
    ts = as_of or _dt(game.date.year, game.date.month, game.date.day)
    tgs = TeamGameStats(
        game_id=game.id,
        team_abbreviation=abbr,
        is_home=is_home,
        pace=pace,
        ortg=ortg,
        drtg=drtg,
        fetched_at=ts,
        as_of=ts,
    )
    session.add(tgs)
    session.flush()
    return tgs


def _add_player(
    session: Session,
    name: str = "Jayson Tatum",
    abbr: str = "BOS",
    pid: str = "111",
) -> Player:
    p = Player(
        player_id=pid,
        name=name,
        team_abbreviation=abbr,
        is_active=True,
        as_of=_dt(2024, 1, 1),
    )
    session.add(p)
    session.flush()
    return p


def _add_player_stats(
    session: Session,
    game: Game,
    player: Player,
    usage: float = 0.28,
    points: int = 25,
    as_of: datetime.datetime | None = None,
) -> PlayerGameStats:
    ts = as_of or _dt(game.date.year, game.date.month, game.date.day)
    pgs = PlayerGameStats(
        game_id=game.id,
        player_id=player.id,
        minutes=30.0,
        points=points,
        usage_pct=usage,
        fetched_at=ts,
        as_of=ts,
    )
    session.add(pgs)
    session.flush()
    return pgs


def _add_injury(
    session: Session,
    player: Player,
    status: str,
    as_of: datetime.datetime,
) -> Injury:
    inj = Injury(
        player_id=player.id,
        status=status,
        source="rotowire",
        ingested_at=as_of,
        as_of=as_of,
    )
    session.add(inj)
    session.flush()
    return inj


def _add_odds(
    session: Session,
    game: Game,
    book: str,
    market: str,
    selection: str,
    price: int,
    snap_dt: datetime.datetime,
) -> OddsSnapshot:
    snap = OddsSnapshot(
        game_id=game.id,
        book=book,
        market=market,
        selection=selection,
        price=price,
        fetched_at=snap_dt,
        as_of=snap_dt,
    )
    session.add(snap)
    session.flush()
    return snap


# ─── pure function tests ──────────────────────────────────────────────────────


def test_haversine_km_zero_when_same_point() -> None:
    assert haversine_km(0.0, 0.0, 0.0, 0.0) == 0.0


def test_haversine_km_approximate_boston_to_la() -> None:
    lat1, lon1 = ARENA_COORDS["BOS"]
    lat2, lon2 = ARENA_COORDS["LAL"]
    dist = haversine_km(lat1, lon1, lat2, lon2)
    assert 4000 < dist < 4500


def test_arena_travel_km_same_team_is_zero() -> None:
    assert arena_travel_km("BOS", "BOS") == 0.0


def test_arena_travel_km_unknown_abbr_is_zero() -> None:
    assert arena_travel_km("XXX", "BOS") == 0.0


# ─── team feature tests ───────────────────────────────────────────────────────


def test_rest_days_returns_correct_count(db: Session) -> None:
    target = _date(2024, 1, 15)
    g = _add_game(db, _date(2024, 1, 12), "BOS", "LAL")
    _add_team_stats(db, g, "BOS", True)
    db.commit()

    result = team_features.rest_days(db, "BOS", target, _dt(2024, 1, 15, 12))
    assert result == 3


def test_rest_days_returns_default_when_no_history(db: Session) -> None:
    result = team_features.rest_days(db, "BOS", _date(2024, 1, 15), _dt(2024, 1, 15, 12))
    assert result == team_features._DEFAULT_REST_DAYS


def test_is_back_to_back_true(db: Session) -> None:
    target = _date(2024, 1, 15)
    g = _add_game(db, _date(2024, 1, 14), "BOS", "LAL")
    _add_team_stats(db, g, "BOS", True)
    db.commit()

    assert team_features.is_back_to_back(db, "BOS", target, _dt(2024, 1, 15, 12)) is True


def test_is_back_to_back_false(db: Session) -> None:
    target = _date(2024, 1, 15)
    g = _add_game(db, _date(2024, 1, 12), "BOS", "LAL")
    _add_team_stats(db, g, "BOS", True)
    db.commit()

    assert team_features.is_back_to_back(db, "BOS", target, _dt(2024, 1, 15, 12)) is False


def test_rolling_pace_averages_last_n_games(db: Session) -> None:
    target = _date(2024, 1, 15)
    for day, pace in [(10, 100.0), (11, 104.0), (12, 106.0)]:
        g = _add_game(db, _date(2024, 1, day), "BOS", "LAL", gid=f"pace{day}")
        _add_team_stats(db, g, "BOS", True, pace=pace)
    db.commit()

    result = team_features.rolling_pace(db, "BOS", target, _dt(2024, 1, 15, 12))
    assert result == pytest.approx((100.0 + 104.0 + 106.0) / 3)


def test_rolling_pace_excludes_stats_recorded_after_as_of(db: Session) -> None:
    # Stats whose as_of is AFTER the prediction moment must not leak through.
    target = _date(2024, 1, 15)
    g = _add_game(db, _date(2024, 1, 12), "BOS", "LAL")
    _add_team_stats(db, g, "BOS", True, pace=120.0, as_of=_dt(2024, 1, 15, 18))
    db.commit()

    result = team_features.rolling_pace(db, "BOS", target, _dt(2024, 1, 15, 12))
    assert result is None


def test_rolling_drtg(db: Session) -> None:
    target = _date(2024, 1, 15)
    for day, drtg in [(10, 105.0), (12, 111.0)]:
        g = _add_game(db, _date(2024, 1, day), "BOS", "LAL", gid=f"drtg{day}")
        _add_team_stats(db, g, "BOS", True, drtg=drtg)
    db.commit()

    result = team_features.rolling_drtg(db, "BOS", target, _dt(2024, 1, 15, 12))
    assert result == pytest.approx((105.0 + 111.0) / 2)


# ─── player feature tests ─────────────────────────────────────────────────────


def test_rolling_usage_averages_games(db: Session) -> None:
    player = _add_player(db)
    target = _date(2024, 1, 15)
    for day, usage in [(10, 0.30), (11, 0.25), (12, 0.28)]:
        g = _add_game(db, _date(2024, 1, day), "BOS", "LAL", gid=f"pu{day}")
        _add_player_stats(db, g, player, usage=usage)
    db.commit()

    result = player_features.rolling_usage(db, player.id, target, _dt(2024, 1, 15, 12))
    assert result == pytest.approx((0.30 + 0.25 + 0.28) / 3)


def test_rolling_usage_excludes_stats_recorded_after_as_of(db: Session) -> None:
    player = _add_player(db)
    g = _add_game(db, _date(2024, 1, 12), "BOS", "LAL")
    _add_player_stats(db, g, player, usage=0.35, as_of=_dt(2024, 1, 15, 18))
    db.commit()

    result = player_features.rolling_usage(db, player.id, _date(2024, 1, 15), _dt(2024, 1, 15, 12))
    assert result is None


def test_current_injury_status_returns_most_recent(db: Session) -> None:
    player = _add_player(db)
    _add_injury(db, player, "questionable", _dt(2024, 1, 14, 10))
    _add_injury(db, player, "out", _dt(2024, 1, 15, 9))
    db.commit()

    status = player_features.current_injury_status(db, player.id, _dt(2024, 1, 15, 12))
    assert status == "out"


def test_current_injury_status_respects_as_of(db: Session) -> None:
    # Injury reported at 14:00 — must be invisible at 12:00
    player = _add_player(db)
    _add_injury(db, player, "out", _dt(2024, 1, 15, 14))
    db.commit()

    status = player_features.current_injury_status(db, player.id, _dt(2024, 1, 15, 12))
    assert status is None


def test_is_player_available_with_no_injury_record(db: Session) -> None:
    player = _add_player(db)
    assert player_features.is_player_available(db, player.id, _dt(2024, 1, 15, 12)) is True


def test_is_player_available_out_is_unavailable(db: Session) -> None:
    player = _add_player(db)
    _add_injury(db, player, "out", _dt(2024, 1, 15, 9))
    db.commit()

    assert player_features.is_player_available(db, player.id, _dt(2024, 1, 15, 12)) is False


def test_team_usage_lost_sums_unavailable_players(db: Session) -> None:
    p1 = _add_player(db, name="Player One", pid="p1")
    p2 = _add_player(db, name="Player Two", pid="p2")
    target = _date(2024, 1, 15)
    for day in [10, 11, 12]:
        g = _add_game(db, _date(2024, 1, day), "BOS", "LAL", gid=f"ul{day}")
        _add_player_stats(db, g, p1, usage=0.30)
        _add_player_stats(db, g, p2, usage=0.20)
    _add_injury(db, p1, "out", _dt(2024, 1, 14))
    # p2 is healthy — no injury record
    db.commit()

    lost = player_features.team_usage_lost(db, "BOS", target, _dt(2024, 1, 15, 12))
    assert lost == pytest.approx(0.30)


# ─── odds feature tests ───────────────────────────────────────────────────────


def test_line_movement_returns_price_delta(db: Session) -> None:
    game = _add_game(db, _date(2024, 1, 15), "BOS", "LAL")
    now = _dt(2024, 1, 15, 12)
    _add_odds(db, game, "draftkings", "h2h", "Boston Celtics", -150, _dt(2024, 1, 15, 8))
    _add_odds(db, game, "draftkings", "h2h", "Boston Celtics", -160, _dt(2024, 1, 15, 11))
    db.commit()

    movement = odds_features.line_movement(db, game.id, "draftkings", "h2h", "Boston Celtics", now)
    assert movement == -10.0


def test_line_movement_returns_none_for_single_snapshot(db: Session) -> None:
    game = _add_game(db, _date(2024, 1, 15), "BOS", "LAL")
    now = _dt(2024, 1, 15, 12)
    _add_odds(db, game, "draftkings", "h2h", "Boston Celtics", -150, _dt(2024, 1, 15, 8))
    db.commit()

    movement = odds_features.line_movement(db, game.id, "draftkings", "h2h", "Boston Celtics", now)
    assert movement is None


def test_opening_price_returns_first_snapshot(db: Session) -> None:
    game = _add_game(db, _date(2024, 1, 15), "BOS", "LAL")
    _add_odds(db, game, "draftkings", "h2h", "Boston Celtics", -150, _dt(2024, 1, 15, 8))
    _add_odds(db, game, "draftkings", "h2h", "Boston Celtics", -160, _dt(2024, 1, 15, 11))
    db.commit()

    price = odds_features.opening_price(db, game.id, "draftkings", "h2h", "Boston Celtics")
    assert price == -150


# ─── builder smoke tests ──────────────────────────────────────────────────────


def test_build_game_features_returns_correct_type(db: Session) -> None:
    game = _add_game(db, _date(2024, 1, 15), "BOS", "LAL")
    db.commit()

    features = build_game_features(db, game, _dt(2024, 1, 15, 12))
    assert isinstance(features, GameFeatures)
    assert features.game_id == game.id
    assert features.home_rest_days == team_features._DEFAULT_REST_DAYS
    assert features.away_rest_days == team_features._DEFAULT_REST_DAYS
    assert features.home_is_b2b is False
    assert features.dk_home_h2h_movement is None
    assert isinstance(features.to_dict(), dict)


def test_build_player_features_returns_correct_type(db: Session) -> None:
    player = _add_player(db)
    game = _add_game(db, _date(2024, 1, 15), "BOS", "LAL")
    db.commit()

    features = build_player_features(db, player, game, _dt(2024, 1, 15, 12))
    assert isinstance(features, PlayerGameFeatures)
    assert features.player_id == player.id
    assert features.is_available is True
    assert features.rolling_usage is None
    assert isinstance(features.to_dict(), dict)
