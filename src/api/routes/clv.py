from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.limiter import limiter
from src.api.schemas import CLVResponse, DailyCLV, MarketBreakdown
from src.tracker.live_clv import live_clv_series, live_clv_summary

router = APIRouter()


@router.get("/clv", response_model=CLVResponse)
@limiter.limit("60/minute")
def get_clv(request: Request, days: int = 30, db: Session = Depends(get_db)) -> CLVResponse:
    summary = live_clv_summary(db, days=days)
    daily_pts, mkt_pts = live_clv_series(db, days=days)
    return CLVResponse(
        days=days,
        n_bets=summary.n_bets,
        n_settled=summary.n_settled,
        mean_clv=summary.mean_clv,
        mean_ev=summary.mean_ev,
        roi=summary.roi,
        win_rate=summary.win_rate,
        daily=[
            DailyCLV(
                date=d.date,
                cumulative_clv=d.cumulative_clv,
                cumulative_ev=d.cumulative_ev,
                n_bets=d.n_bets,
            )
            for d in daily_pts
        ],
        by_market=[
            MarketBreakdown(
                market=m.market,
                n_bets=m.n_bets,
                n_settled=m.n_settled,
                mean_clv=m.mean_clv,
                mean_ev=m.mean_ev,
            )
            for m in mkt_pts
        ],
    )
