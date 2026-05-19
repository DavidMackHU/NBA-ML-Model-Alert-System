import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import OddsSnapshot


def line_movement(
    session: Session,
    game_id: int,
    book: str,
    market: str,
    selection: str,
    as_of: datetime.datetime,
    hours_back: int = 24,
) -> Optional[float]:
    """Return price delta (latest - earliest) within the look-back window.

    Positive value means the line moved in favour of the selection (shorter odds).
    Returns None when fewer than two snapshots exist in the window.
    """
    window_start = as_of - datetime.timedelta(hours=hours_back)
    snaps = (
        session.query(OddsSnapshot)
        .filter(
            OddsSnapshot.game_id == game_id,
            OddsSnapshot.book == book,
            OddsSnapshot.market == market,
            OddsSnapshot.selection == selection,
            OddsSnapshot.as_of >= window_start,
            OddsSnapshot.as_of <= as_of,
        )
        .order_by(OddsSnapshot.as_of.asc())
        .all()
    )
    if len(snaps) < 2:
        return None
    return float(snaps[-1].price - snaps[0].price)


def opening_price(
    session: Session,
    game_id: int,
    book: str,
    market: str,
    selection: str,
) -> Optional[int]:
    """Return the first recorded price for a market/selection, regardless of window."""
    snap = (
        session.query(OddsSnapshot)
        .filter(
            OddsSnapshot.game_id == game_id,
            OddsSnapshot.book == book,
            OddsSnapshot.market == market,
            OddsSnapshot.selection == selection,
        )
        .order_by(OddsSnapshot.as_of.asc())
        .first()
    )
    return snap.price if snap else None
