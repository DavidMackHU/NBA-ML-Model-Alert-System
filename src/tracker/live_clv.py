"""Live CLV summary — aggregate settled-bet metrics for the dashboard."""

import dataclasses
import datetime
from collections import defaultdict

from sqlalchemy.orm import Session

from src.db.models import Alert, BetsLog


@dataclasses.dataclass
class DailyCLVPoint:
    date: str
    cumulative_clv: float
    cumulative_ev: float
    n_bets: int


@dataclasses.dataclass
class MarketBreakdownPoint:
    market: str
    n_bets: int
    n_settled: int
    mean_clv: float
    mean_ev: float


@dataclasses.dataclass
class LiveCLVSummary:
    n_bets: int
    n_settled: int
    mean_clv: float  # mean(pin_closing_fair_p - dk_implied_p); primary metric
    mean_ev: float  # mean ev_pct at alert time; modeled edge
    roi: float  # flat-bet ROI on settled bets
    win_rate: float  # fraction of settled bets that won


def live_clv_summary(
    session: Session,
    days: int = 30,
    now: datetime.datetime | None = None,
) -> LiveCLVSummary:
    """Return aggregated CLV metrics for bets placed in the last N days.

    Accepts an optional ``now`` for testing; defaults to current UTC time.
    """
    if now is None:
        now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(days=days)

    rows = (
        session.query(Alert, BetsLog)
        .join(BetsLog, Alert.id == BetsLog.alert_id)
        .filter(Alert.alert_time >= cutoff)
        .all()
    )

    if not rows:
        return LiveCLVSummary(
            n_bets=0, n_settled=0, mean_clv=0.0, mean_ev=0.0, roi=0.0, win_rate=0.0
        )

    clvs = [b.clv for _, b in rows if b.clv is not None]
    evs = [a.ev_pct for a, _ in rows]
    settled = [(a, b) for a, b in rows if b.outcome is not None]

    roi = 0.0
    win_rate = 0.0
    if settled:
        pnls = [
            (a.dk_price / 100.0 if a.dk_price > 0 else 100.0 / abs(a.dk_price))
            if b.outcome == "win"
            else -1.0
            for a, b in settled
        ]
        roi = sum(pnls) / len(settled)
        win_rate = sum(1 for _, b in settled if b.outcome == "win") / len(settled)

    return LiveCLVSummary(
        n_bets=len(rows),
        n_settled=len(settled),
        mean_clv=sum(clvs) / len(clvs) if clvs else 0.0,
        mean_ev=sum(evs) / len(evs) if evs else 0.0,
        roi=roi,
        win_rate=win_rate,
    )


def live_clv_series(
    session: Session,
    days: int = 30,
    now: datetime.datetime | None = None,
) -> tuple[list[DailyCLVPoint], list[MarketBreakdownPoint]]:
    """Return daily cumulative CLV series and per-market breakdown for the last N days.

    Single DB query; two passes in Python — one for the time series, one for market aggregates.
    """
    if now is None:
        now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(days=days)

    rows = (
        session.query(Alert, BetsLog)
        .join(BetsLog, Alert.id == BetsLog.alert_id)
        .filter(Alert.alert_time >= cutoff)
        .order_by(BetsLog.settled_at)
        .all()
    )

    if not rows:
        return [], []

    # daily cumulative (expanding mean) — settled bets with non-null CLV only
    by_date: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for alert, bet in rows:
        if bet.settled_at is not None and bet.clv is not None:
            date_str = bet.settled_at.strftime("%Y-%m-%d")
            by_date[date_str].append((alert.ev_pct, bet.clv))

    all_clvs: list[float] = []
    all_evs: list[float] = []
    daily: list[DailyCLVPoint] = []
    for date_str in sorted(by_date.keys()):
        pairs = by_date[date_str]
        all_clvs.extend(c for _, c in pairs)
        all_evs.extend(e for e, _ in pairs)
        daily.append(
            DailyCLVPoint(
                date=date_str,
                cumulative_clv=sum(all_clvs) / len(all_clvs),
                cumulative_ev=sum(all_evs) / len(all_evs),
                n_bets=len(all_clvs),
            )
        )

    # per-market breakdown — all bets in window
    mkt_data: dict[str, dict] = defaultdict(
        lambda: {"n_bets": 0, "n_settled": 0, "clvs": [], "evs": []}
    )
    for alert, bet in rows:
        m = mkt_data[alert.market]
        m["n_bets"] += 1
        if bet.outcome is not None:
            m["n_settled"] += 1
        if bet.clv is not None:
            m["clvs"].append(bet.clv)
        m["evs"].append(alert.ev_pct)

    breakdown = [
        MarketBreakdownPoint(
            market=mkt,
            n_bets=d["n_bets"],
            n_settled=d["n_settled"],
            mean_clv=sum(d["clvs"]) / len(d["clvs"]) if d["clvs"] else 0.0,
            mean_ev=sum(d["evs"]) / len(d["evs"]),
        )
        for mkt, d in sorted(mkt_data.items())
    ]

    return daily, breakdown
