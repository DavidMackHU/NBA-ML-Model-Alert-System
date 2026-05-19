import asyncio
import datetime
from typing import Any

import httpx
import structlog
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.db.models import Game, OddsSnapshot

log = structlog.get_logger()

SPORT = "basketball_nba"
BASE_URL = "https://api.the-odds-api.com/v4"
BOOKMAKERS = ["draftkings", "pinnacle"]
MARKETS = ["h2h", "player_points"]
REGIONS = "us"


async def _get(url: str, params: dict[str, Any]) -> Any:
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                log.info(
                    "odds_api_request",
                    remaining=resp.headers.get("x-requests-remaining", "?"),
                    used=resp.headers.get("x-requests-used", "?"),
                )
                return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                log.error("odds_api_unauthorized", status=401)
                raise
            if exc.response.status_code == 422:
                log.error("odds_api_unprocessable", status=422, body=exc.response.text)
                raise
            if attempt == 2:
                raise
            await asyncio.sleep(2**attempt)
        except httpx.TransportError:
            if attempt == 2:
                raise
            await asyncio.sleep(2**attempt)


async def fetch_market(market: str, api_key: str) -> list[dict]:
    url = f"{BASE_URL}/sports/{SPORT}/odds"
    params = {
        "apiKey": api_key,
        "regions": REGIONS,
        "markets": market,
        "oddsFormat": "american",
        "bookmakers": ",".join(BOOKMAKERS),
    }
    return await _get(url, params)


def _upsert_game(session: Session, event: dict, as_of: datetime.datetime) -> Game:
    game = session.query(Game).filter(Game.game_id == event["id"]).first()
    if game is not None:
        return game
    tipoff = datetime.datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
    game = Game(
        game_id=event["id"],
        date=tipoff.date(),
        home_team=event["home_team"][:100],
        away_team=event["away_team"][:100],
        tipoff_utc=tipoff,
        status="scheduled",
        fetched_at=as_of,
        as_of=as_of,
    )
    session.add(game)
    session.flush()
    return game


def _parse_selection(outcome: dict) -> tuple[str, float | None]:
    name = outcome["name"].strip()
    description = outcome.get("description", "").strip()
    selection = f"{name} {description}" if description else name
    return selection[:100], outcome.get("point")


def store_snapshots(
    session: Session,
    events: list[dict],
    market: str,
    as_of: datetime.datetime,
) -> int:
    count = 0
    for event in events:
        game = _upsert_game(session, event, as_of)
        for bm in event.get("bookmakers", []):
            if bm["key"] not in BOOKMAKERS:
                continue
            for mkt in bm.get("markets", []):
                if mkt["key"] != market:
                    continue
                for outcome in mkt.get("outcomes", []):
                    selection, line = _parse_selection(outcome)
                    session.add(
                        OddsSnapshot(
                            game_id=game.id,
                            book=bm["key"],
                            market=market,
                            selection=selection,
                            line=line,
                            price=int(outcome["price"]),
                            fetched_at=as_of,
                            as_of=as_of,
                        )
                    )
                    count += 1
    session.commit()
    log.info("snapshots_stored", market=market, count=count)
    return count


async def run_odds_ingestion(session: Session) -> dict[str, int]:
    """Fetch h2h and player_points for DK + Pinnacle and persist all snapshots."""
    settings = get_settings()
    if not settings.odds_api_key:
        log.warning("odds_api_key_missing", msg="ODDS_API_KEY not set; skipping")
        return {}
    as_of = datetime.datetime.now(tz=datetime.timezone.utc)
    results: dict[str, int] = {}
    for market in MARKETS:
        events = await fetch_market(market, settings.odds_api_key)
        results[market] = store_snapshots(session, events, market, as_of)
    return results
