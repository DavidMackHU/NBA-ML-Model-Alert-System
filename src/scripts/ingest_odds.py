"""Hourly: ingest odds then run edge detection and fire Telegram alerts.

Slate-aware: exits early when no games are recorded for today, conserving
The Odds API request budget (500 req/month free tier).
"""

import asyncio
import datetime

import structlog
from sqlalchemy.orm import Session

from src.alerts.telegram import fire_alert
from src.config.settings import get_settings
from src.db.models import Game, ModelPrediction
from src.db.session import get_session_factory
from src.edge.devig import latest_market_odds
from src.edge.ev import compute_edges
from src.ingestion.odds import run_odds_ingestion
from src.scheduler.slate import alert_already_fired, has_games_today, upcoming_game_ids

log = structlog.get_logger()

ALERT_MARKETS = ["h2h"]


async def _detect_and_alert(
    session: Session,
    date: datetime.date,
    bot_token: str,
    chat_id: str,
    ev_threshold: float,
) -> int:
    as_of = datetime.datetime.now(tz=datetime.timezone.utc)
    alert_count = 0
    for game_id in upcoming_game_ids(session, date):
        game = session.get(Game, game_id)
        for market in ALERT_MARKETS:
            preds = (
                session.query(ModelPrediction)
                .filter(
                    ModelPrediction.game_id == game_id,
                    ModelPrediction.market == market,
                    ModelPrediction.as_of <= as_of,
                )
                .all()
            )
            if not preds:
                continue
            model_preds = {p.selection: p.model_p for p in preds}
            dk_odds = latest_market_odds(session, game_id, "draftkings", market, as_of)
            pin_odds = latest_market_odds(session, game_id, "pinnacle", market, as_of)
            if not dk_odds or not pin_odds:
                continue
            edges = compute_edges(game_id, market, dk_odds, pin_odds, model_preds, ev_threshold)
            for edge in edges:
                if alert_already_fired(session, game_id, market, edge.selection):
                    continue
                await fire_alert(session, game, edge, as_of, bot_token, chat_id)
                alert_count += 1
                log.info(
                    "alert_fired",
                    game_id=game_id,
                    market=market,
                    selection=edge.selection,
                    ev_pct=round(edge.ev_pct, 4),
                )
    return alert_count


async def run() -> None:
    settings = get_settings()
    session_factory = get_session_factory()
    today = datetime.date.today()

    with session_factory() as session:
        if not has_games_today(session, today):
            log.info("odds_poll_skipped", reason="no_games_today", date=str(today))
            return

        counts = await run_odds_ingestion(session)
        log.info("odds_ingestion_done", counts=counts)

        if settings.telegram_bot_token:
            n = await _detect_and_alert(
                session,
                today,
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                settings.ev_threshold,
            )
            log.info("edge_detection_done", alerts_fired=n)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
