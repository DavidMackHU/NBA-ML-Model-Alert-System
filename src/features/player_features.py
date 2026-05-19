import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import Game, Injury, Player, PlayerGameStats

UNAVAILABLE_STATUSES = {"out", "doubtful"}


def get_player_game_history(
    session: Session,
    player_id: int,
    before_date: datetime.date,
    as_of: datetime.datetime,
    n: int = 20,
) -> list[PlayerGameStats]:
    """Return the last n completed game stat rows for a player.

    Enforces point-in-time discipline: only games before before_date whose
    stats were recorded at or before as_of are included.
    """
    return (
        session.query(PlayerGameStats)
        .join(Game, Game.id == PlayerGameStats.game_id)
        .filter(
            PlayerGameStats.player_id == player_id,
            Game.date < before_date,
            PlayerGameStats.as_of <= as_of,
        )
        .order_by(Game.date.desc())
        .limit(n)
        .all()
    )


def rolling_usage(
    session: Session,
    player_id: int,
    before_date: datetime.date,
    as_of: datetime.datetime,
    n: int = 10,
) -> Optional[float]:
    rows = get_player_game_history(session, player_id, before_date, as_of, n=n)
    values = [r.usage_pct for r in rows if r.usage_pct is not None]
    return sum(values) / len(values) if values else None


def rolling_points(
    session: Session,
    player_id: int,
    before_date: datetime.date,
    as_of: datetime.datetime,
    n: int = 10,
) -> Optional[float]:
    rows = get_player_game_history(session, player_id, before_date, as_of, n=n)
    values = [r.points for r in rows if r.points is not None]
    return sum(values) / len(values) if values else None


def current_injury_status(
    session: Session,
    player_id: int,
    as_of: datetime.datetime,
) -> Optional[str]:
    """Return the most recent injury status at or before as_of, or None if no record."""
    injury = (
        session.query(Injury)
        .filter(Injury.player_id == player_id, Injury.as_of <= as_of)
        .order_by(Injury.as_of.desc())
        .first()
    )
    return injury.status if injury else None


def is_player_available(
    session: Session,
    player_id: int,
    as_of: datetime.datetime,
) -> bool:
    status = current_injury_status(session, player_id, as_of)
    return status not in UNAVAILABLE_STATUSES


def team_usage_lost(
    session: Session,
    team_abbr: str,
    before_date: datetime.date,
    as_of: datetime.datetime,
) -> float:
    """Return the sum of rolling usage% for players on team_abbr who are out or doubtful.

    Represents how much of the team's normal offensive load is unavailable.
    """
    players = (
        session.query(Player)
        .filter(
            Player.team_abbreviation == team_abbr,
            Player.is_active == True,  # noqa: E712
        )
        .all()
    )
    lost = 0.0
    for player in players:
        if is_player_available(session, player.id, as_of):
            continue
        usage = rolling_usage(session, player.id, before_date, as_of, n=10)
        if usage is not None:
            lost += usage
    return lost
