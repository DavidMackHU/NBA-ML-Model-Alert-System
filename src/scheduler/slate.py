import datetime

from sqlalchemy.orm import Session

from src.db.models import Alert, Game


def has_games_today(session: Session, date: datetime.date) -> bool:
    """Return True if any games (any status) are recorded for this date."""
    return session.query(Game).filter(Game.date == date).count() > 0


def upcoming_game_ids(session: Session, date: datetime.date) -> list[int]:
    """Return IDs of non-final games for a given date."""
    return [
        g.id
        for g in session.query(Game)
        .filter(
            Game.date == date,
            Game.status.in_(["scheduled", "in_progress"]),
        )
        .all()
    ]


def alert_already_fired(session: Session, game_id: int, market: str, selection: str) -> bool:
    """Return True if an active alert already exists for this game+market+selection.

    Used to prevent re-alerting the same edge on every hourly odds poll.
    """
    return (
        session.query(Alert)
        .filter_by(game_id=game_id, market=market, selection=selection, status="active")
        .first()
    ) is not None
