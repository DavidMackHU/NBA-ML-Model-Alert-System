import dataclasses
import datetime

import scipy.optimize
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from src.db.models import OddsSnapshot


def american_to_raw_prob(price: int) -> float:
    """Convert American odds to raw (overround-inclusive) implied probability."""
    if price > 0:
        return 100.0 / (price + 100.0)
    return abs(price) / (abs(price) + 100.0)


def _power_residual(k: float, raw_probs: list[float]) -> float:
    return sum(p**k for p in raw_probs) - 1.0


def devig_power(prices: list[int]) -> list[float]:
    """Remove vig via the power method.

    Finds k such that sum(raw_p_i ^ k) = 1, then fair_p_i = raw_p_i ^ k.
    Works for any number of outcomes; designed for 2-outcome markets (h2h, over/under).

    When the market has no overround (sum of raw probs ≤ 1), falls back to
    simple normalisation so the caller always gets a valid probability vector.

    Returns fair probabilities in the same order as input prices.
    """
    if not prices:
        raise ValueError("prices must be non-empty")
    raw_probs = [american_to_raw_prob(p) for p in prices]
    total_raw = sum(raw_probs)
    if total_raw <= 1.0:
        return [p / total_raw for p in raw_probs]
    k = scipy.optimize.brentq(_power_residual, 0.001, 100.0, args=(raw_probs,))
    return [p**k for p in raw_probs]


@dataclasses.dataclass
class MarketOdds:
    selection: str
    book: str
    price: int
    raw_prob: float
    fair_prob: float


def latest_market_odds(
    session: Session,
    game_id: int,
    book: str,
    market: str,
    as_of: datetime.datetime,
) -> list[MarketOdds]:
    """Return de-vigged MarketOdds for all selections in a book/market at as_of.

    Uses the most recent snapshot per selection at or before as_of.
    Returns an empty list when fewer than 2 sides are present (power method
    requires at least 2 outcomes to solve for k).
    """
    subq = (
        session.query(
            OddsSnapshot.selection,
            func.max(OddsSnapshot.fetched_at).label("max_fa"),
        )
        .filter(
            OddsSnapshot.game_id == game_id,
            OddsSnapshot.book == book,
            OddsSnapshot.market == market,
            OddsSnapshot.as_of <= as_of,
        )
        .group_by(OddsSnapshot.selection)
        .subquery()
    )

    rows = (
        session.query(OddsSnapshot)
        .join(
            subq,
            and_(
                OddsSnapshot.selection == subq.c.selection,
                OddsSnapshot.fetched_at == subq.c.max_fa,
            ),
        )
        .filter(
            OddsSnapshot.game_id == game_id,
            OddsSnapshot.book == book,
            OddsSnapshot.market == market,
        )
        .all()
    )

    if len(rows) < 2:
        return []

    prices = [r.price for r in rows]
    fair_probs = devig_power(prices)
    raw_probs = [american_to_raw_prob(p) for p in prices]

    return [
        MarketOdds(
            selection=r.selection,
            book=book,
            price=r.price,
            raw_prob=rp,
            fair_prob=fp,
        )
        for r, rp, fp in zip(rows, raw_probs, fair_probs)
    ]
