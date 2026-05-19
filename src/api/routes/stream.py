import asyncio
import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from src.api.deps import get_db
from src.api.limiter import limiter
from src.api.schemas import AlertSummary
from src.db.models import Alert, Game

router = APIRouter()

_POLL_SECONDS = 5
_HEARTBEAT_SECONDS = 20
_LIVE_WINDOW_HOURS = 6


def _new_alerts(session: Session, since: datetime.datetime) -> list[tuple[Alert, Game]]:
    return (
        session.query(Alert, Game)
        .join(Game, Alert.game_id == Game.id)
        .filter(Alert.status == "active", Alert.alert_time > since)
        .order_by(Alert.alert_time.asc())
        .all()
    )


def _to_sse(alert: Alert, game: Game) -> ServerSentEvent:
    payload = AlertSummary(
        id=alert.id,
        game_id=alert.game_id,
        market=alert.market,
        selection=alert.selection,
        dk_price=alert.dk_price,
        dk_implied_p=alert.dk_implied_p,
        pin_price=alert.pin_price,
        pin_implied_p=alert.pin_implied_p,
        model_p=alert.model_p,
        ev_pct=alert.ev_pct,
        edge_pin_vs_dk=alert.edge_pin_vs_dk,
        alert_time=alert.alert_time,
        time_to_tip_seconds=alert.time_to_tip_seconds,
        status=alert.status,
        home_team=game.home_team,
        away_team=game.away_team,
        tipoff_utc=game.tipoff_utc,
    )
    return ServerSentEvent(
        data=payload.model_dump_json(),
        event="alert",
        id=str(alert.id),
    )


async def _event_generator(
    request: Request,
    db: Session,
) -> AsyncGenerator[ServerSentEvent, None]:
    last_seen = datetime.datetime.utcnow() - datetime.timedelta(hours=_LIVE_WINDOW_HOURS)
    while True:
        if await request.is_disconnected():
            break
        for alert, game in _new_alerts(db, last_seen):
            last_seen = alert.alert_time
            yield _to_sse(alert, game)
        await asyncio.sleep(_POLL_SECONDS)


@router.get("/stream/alerts")
@limiter.limit("60/minute")
async def stream_alerts(
    request: Request,
    db: Session = Depends(get_db),
) -> EventSourceResponse:
    return EventSourceResponse(
        _event_generator(request, db),
        ping=_HEARTBEAT_SECONDS,
    )
