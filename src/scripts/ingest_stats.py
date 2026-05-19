"""Daily: sync box scores and advanced stats for yesterday's completed games."""

import asyncio

import httpx
import structlog

from src.db.session import get_session_factory
from src.ingestion.nba_stats import run_stats_ingestion

log = structlog.get_logger()


async def run() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            summary = await run_stats_ingestion(session)
            log.info("stats_ingestion_done", **summary)
        except httpx.TimeoutException:
            log.warning("stats_ingestion_skipped", reason="NBA Stats API timeout after retries")
        except httpx.HTTPStatusError as exc:
            log.warning(
                "stats_ingestion_skipped",
                reason="NBA Stats API error",
                status=exc.response.status_code,
            )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
