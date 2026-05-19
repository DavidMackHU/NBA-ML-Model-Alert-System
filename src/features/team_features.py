import datetime
import math
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import Game, TeamGameStats

# NBA arena coordinates (latitude, longitude)
ARENA_COORDS: dict[str, tuple[float, float]] = {
    "ATL": (33.7573, -84.3963),
    "BOS": (42.3662, -71.0621),
    "BKN": (40.6826, -73.9754),
    "CHA": (35.2251, -80.8392),
    "CHI": (41.8807, -87.6742),
    "CLE": (41.4965, -81.6882),
    "DAL": (32.7905, -96.8103),
    "DEN": (39.7487, -105.0077),
    "DET": (42.3411, -83.0558),
    "GSW": (37.7680, -122.3877),
    "HOU": (29.7508, -95.3621),
    "IND": (39.7640, -86.1555),
    "LAC": (33.9425, -118.1082),
    "LAL": (34.0430, -118.2673),
    "MEM": (35.1381, -90.0505),
    "MIA": (25.7814, -80.1870),
    "MIL": (43.0450, -87.9171),
    "MIN": (44.9795, -93.2760),
    "NOP": (29.9490, -90.0823),
    "NYK": (40.7505, -73.9934),
    "OKC": (35.4634, -97.5151),
    "ORL": (28.5392, -81.3839),
    "PHI": (39.9012, -75.1720),
    "PHX": (33.4457, -112.0712),
    "POR": (45.5316, -122.6668),
    "SAC": (38.5805, -121.4997),
    "SAS": (29.4271, -98.4375),
    "TOR": (43.6435, -79.3791),
    "UTA": (40.7683, -111.9011),
    "WAS": (38.8981, -77.0209),
}

_DEFAULT_REST_DAYS = 7  # assumed when no prior game is found in the lookback window


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def arena_travel_km(from_abbr: str, to_abbr: str) -> float:
    if from_abbr == to_abbr:
        return 0.0
    if from_abbr not in ARENA_COORDS or to_abbr not in ARENA_COORDS:
        return 0.0
    lat1, lon1 = ARENA_COORDS[from_abbr]
    lat2, lon2 = ARENA_COORDS[to_abbr]
    return haversine_km(lat1, lon1, lat2, lon2)


def _get_team_game_history(
    session: Session,
    team_abbr: str,
    before_date: datetime.date,
    as_of: datetime.datetime,
    lookback_days: int = 90,
) -> list[tuple[Game, TeamGameStats]]:
    """Return (Game, TeamGameStats) pairs for a team's recent completed games.

    Enforces point-in-time discipline: only games before before_date whose
    stats were recorded at or before as_of are included.
    """
    cutoff = before_date - datetime.timedelta(days=lookback_days)
    return (
        session.query(Game, TeamGameStats)
        .join(TeamGameStats, TeamGameStats.game_id == Game.id)
        .filter(
            TeamGameStats.team_abbreviation == team_abbr,
            Game.date < before_date,
            Game.date >= cutoff,
            TeamGameStats.as_of <= as_of,
        )
        .order_by(Game.date.desc())
        .all()
    )


def rest_days(
    session: Session,
    team_abbr: str,
    before_date: datetime.date,
    as_of: datetime.datetime,
) -> int:
    history = _get_team_game_history(session, team_abbr, before_date, as_of)
    if not history:
        return _DEFAULT_REST_DAYS
    last_game, _ = history[0]
    return (before_date - last_game.date).days


def is_back_to_back(
    session: Session,
    team_abbr: str,
    before_date: datetime.date,
    as_of: datetime.datetime,
) -> bool:
    return rest_days(session, team_abbr, before_date, as_of) == 1


def _last_game_location(
    session: Session,
    team_abbr: str,
    history: list[tuple[Game, TeamGameStats]],
) -> str:
    """Return the arena abbreviation where the team was after their most recent game."""
    if not history:
        return team_abbr
    last_game, last_tgs = history[0]
    if last_tgs.is_home:
        return team_abbr
    # Away game — find the home team to identify which arena they visited
    home_tgs = (
        session.query(TeamGameStats)
        .filter(
            TeamGameStats.game_id == last_game.id,
            TeamGameStats.is_home == True,  # noqa: E712
        )
        .first()
    )
    return home_tgs.team_abbreviation if home_tgs else team_abbr


def travel_km_for_game(
    session: Session,
    team_abbr: str,
    is_home: bool,
    opponent_abbr: str,
    before_date: datetime.date,
    as_of: datetime.datetime,
) -> float:
    dest_abbr = team_abbr if is_home else opponent_abbr
    history = _get_team_game_history(session, team_abbr, before_date, as_of, lookback_days=7)
    origin_abbr = _last_game_location(session, team_abbr, history)
    return arena_travel_km(origin_abbr, dest_abbr)


def _rolling_stat(
    session: Session,
    team_abbr: str,
    before_date: datetime.date,
    as_of: datetime.datetime,
    n: int,
    attr: str,
) -> Optional[float]:
    history = _get_team_game_history(session, team_abbr, before_date, as_of)[:n]
    values = [getattr(tgs, attr) for _, tgs in history if getattr(tgs, attr) is not None]
    return sum(values) / len(values) if values else None


def rolling_pace(
    session: Session,
    team_abbr: str,
    before_date: datetime.date,
    as_of: datetime.datetime,
    n: int = 10,
) -> Optional[float]:
    return _rolling_stat(session, team_abbr, before_date, as_of, n, "pace")


def rolling_drtg(
    session: Session,
    team_abbr: str,
    before_date: datetime.date,
    as_of: datetime.datetime,
    n: int = 10,
) -> Optional[float]:
    return _rolling_stat(session, team_abbr, before_date, as_of, n, "drtg")


def rolling_ortg(
    session: Session,
    team_abbr: str,
    before_date: datetime.date,
    as_of: datetime.datetime,
    n: int = 10,
) -> Optional[float]:
    return _rolling_stat(session, team_abbr, before_date, as_of, n, "ortg")
