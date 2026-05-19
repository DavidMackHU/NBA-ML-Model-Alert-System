import datetime
import zoneinfo

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.limiter import limiter
from src.api.schemas import BestEdge, TodayGame, TodaySlateResponse
from src.db.models import Alert, Game

router = APIRouter()

_ET = zoneinfo.ZoneInfo("America/New_York")
_STALE_HOURS = 6
_CACHE_SECONDS = 30


def _slate_window_naive_utc(
    now_et: datetime.datetime,
) -> tuple[datetime.datetime, datetime.datetime]:
    """Return (start, end) as naive UTC for the 6am-ET-anchored slate window.

    Naive UTC is used for DB compatibility — SQLite stores TIMESTAMP without tz.
    """
    slate_date = now_et.date()
    utc = datetime.timezone.utc
    start = (
        datetime.datetime.combine(slate_date, datetime.time(6, 0))
        .replace(tzinfo=_ET)
        .astimezone(utc)
        .replace(tzinfo=None)
    )
    end = (
        datetime.datetime.combine(slate_date + datetime.timedelta(days=1), datetime.time(6, 0))
        .replace(tzinfo=_ET)
        .astimezone(utc)
        .replace(tzinfo=None)
    )
    return start, end


def _to_et(dt: datetime.datetime) -> datetime.datetime:
    """Convert a datetime (naive UTC or tz-aware) to ET."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(_ET)


def _best_alerts_by_game(
    session: Session,
    stale_cutoff: datetime.datetime,
) -> dict[int, Alert]:
    """Return {game_id: Alert} mapping the highest-EV active alert per game.

    Filters: status=active, alert_time within stale window, and model/Pinnacle
    both agree against DK (same-sign divergence from dk_implied_p).
    """
    rn_subq = (
        select(
            Alert.id.label("alert_id"),
            Alert.game_id.label("game_id"),
            func.row_number()
            .over(partition_by=Alert.game_id, order_by=Alert.ev_pct.desc())
            .label("rn"),
        )
        .where(
            Alert.status == "active",
            Alert.alert_time >= stale_cutoff,
            # Same-sign check without func.sign() — works in SQLite and Postgres
            (Alert.model_p - Alert.dk_implied_p) * (Alert.pin_implied_p - Alert.dk_implied_p) > 0,
        )
        .subquery()
    )
    rows = (
        session.execute(
            select(Alert).join(
                rn_subq,
                (Alert.id == rn_subq.c.alert_id) & (rn_subq.c.rn == 1),
            )
        )
        .scalars()
        .all()
    )
    return {a.game_id: a for a in rows}


def _build_best_edge(alert: Alert) -> BestEdge:
    return BestEdge(
        alert_id=alert.id,
        market=alert.market,
        selection=alert.selection,
        ev_pct=alert.ev_pct,
        model_p=alert.model_p,
        dk_implied_p=alert.dk_implied_p,
        pin_implied_p=alert.pin_implied_p,
        dk_price=alert.dk_price,
        pin_price=alert.pin_price,
        edge_pin_vs_dk=alert.edge_pin_vs_dk,
        alert_time=alert.alert_time,
    )


@router.get("/today", response_model=TodaySlateResponse)
@limiter.limit("60/minute")
def today_slate(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TodaySlateResponse:
    now_utc = datetime.datetime.utcnow()
    now_et = datetime.datetime.now(_ET)
    start_utc, end_utc = _slate_window_naive_utc(now_et)
    stale_cutoff = now_utc - datetime.timedelta(hours=_STALE_HOURS)

    games = (
        db.execute(
            select(Game)
            .where(Game.tipoff_utc.between(start_utc, end_utc))
            .order_by(Game.tipoff_utc.asc())
        )
        .scalars()
        .all()
    )

    best = _best_alerts_by_game(db, stale_cutoff)

    today_games = [
        TodayGame(
            game_id=g.id,
            home_team=g.home_team,
            away_team=g.away_team,
            tipoff_utc=g.tipoff_utc,
            tipoff_local_et=_to_et(g.tipoff_utc),
            status=g.status,
            home_score=g.home_score,
            away_score=g.away_score,
            best_edge=_build_best_edge(best[g.id]) if g.id in best else None,
        )
        for g in games
    ]

    response.headers["Cache-Control"] = f"public, max-age={_CACHE_SECONDS}"
    return TodaySlateResponse(
        slate_date=now_et.date(),
        games=today_games,
        generated_at=now_utc,
    )
