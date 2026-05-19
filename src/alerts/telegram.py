import datetime

import telegram
from sqlalchemy.orm import Session

from src.db.models import Alert, Game
from src.edge.ev import EdgeResult, store_alert


def _format_time_to_tip(seconds: int) -> str:
    if seconds <= 0:
        return "at/past tipoff"
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def format_message(game: Game, alert: Alert) -> str:
    market_label = "Moneyline" if alert.market == "h2h" else "Player Points"
    tip_str = _format_time_to_tip(alert.time_to_tip_seconds)
    return (
        f"<b>+EV Candidate — {market_label}</b>\n"
        f"{game.away_team} @ {game.home_team}\n\n"
        f"<b>Selection:</b> {alert.selection}\n"
        f"<b>DK:</b> {alert.dk_price:+d} (fair {alert.dk_implied_p * 100:.1f}%)\n"
        f"<b>Pin:</b> {alert.pin_price:+d} (fair {alert.pin_implied_p * 100:.1f}%)\n"
        f"<b>Model P:</b> {alert.model_p * 100:.1f}%\n"
        f"<b>EV:</b> {alert.ev_pct * 100:+.1f}%  "
        f"<b>Pin-vs-DK:</b> {alert.edge_pin_vs_dk * 100:+.1f}pp\n"
        f"<b>Time to tip:</b> {tip_str}\n"
        f"<b>Alert ID:</b> {alert.id}"
    )


async def send_alert(bot_token: str, chat_id: str, text: str) -> None:
    async with telegram.Bot(bot_token) as bot:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


async def fire_alert(
    session: Session,
    game: Game,
    edge: EdgeResult,
    as_of: datetime.datetime,
    bot_token: str,
    chat_id: str,
) -> Alert:
    """Store the edge alert to DB, send the Telegram message, then commit.

    Session is committed only after a successful send. On Telegram failure
    the exception propagates and the session remains uncommitted.
    """
    alert = store_alert(session, game, edge, as_of)
    text = format_message(game, alert)
    await send_alert(bot_token, chat_id, text)
    session.commit()
    return alert
