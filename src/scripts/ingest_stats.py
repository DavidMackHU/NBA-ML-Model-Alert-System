"""Daily: sync box scores and advanced stats for yesterday's completed games."""

import asyncio

import structlog

from src.db.session import get_session_factory
from src.ingestion.nba_stats import run_stats_ingestion

log = structlog.get_logger()


async def run() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        summary = await run_stats_ingestion(session)
        log.info("stats_ingestion_done", **summary)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
