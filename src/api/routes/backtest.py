import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.limiter import limiter
from src.api.schemas import BacktestFilters, BacktestResponse, EdgeBucket, CLVBucket
from src.backtest.engine import (
    Scenario,
    aggregate,
    apply_scenario,
    collect_bets,
    compute_distributions,
)

router = APIRouter()


def _season_to_dates(season: int) -> tuple[datetime.date, datetime.date]:
    return datetime.date(season - 1, 10, 1), datetime.date(season, 7, 1)


@router.get("/backtest", response_model=BacktestResponse)
@limiter.limit("60/minute")
def get_backtest(
    request: Request,
    season: int | None = None,
    market: str = "h2h",
    threshold: float = 0.03,
    scenario: str = "perfect",
    db: Session = Depends(get_db),
) -> BacktestResponse:
    try:
        sc = Scenario(scenario)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{scenario}'")

    if season is not None:
        start, end = _season_to_dates(season)
    else:
        start = datetime.date(2020, 1, 1)
        end = datetime.date.today()

    bets = collect_bets(db, start, end, ev_threshold=threshold, market=market)
    scenario_bets = apply_scenario(bets, sc)
    result = aggregate(scenario_bets)
    edge_dist_raw, clv_dist_raw = compute_distributions(scenario_bets)

    return BacktestResponse(
        filters=BacktestFilters(
            season=season, market=market, threshold=threshold, scenario=scenario
        ),
        n_bets=result.n_bets,
        n_settled=result.n_settled,
        mean_clv=result.mean_clv,
        mean_ev=result.mean_ev,
        roi=result.roi,
        hit_rate=result.hit_rate,
        brier_score=result.brier_score,
        edge_distribution=[EdgeBucket(**e) for e in edge_dist_raw],
        clv_distribution=[CLVBucket(**c) for c in clv_dist_raw],
    )
