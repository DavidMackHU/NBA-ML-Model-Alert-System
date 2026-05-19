"""Every 30 min: sync injury statuses from Rotowire RSS and NBA official report."""

import asyncio

import structlog

from src.db.session import get_session_factory
from src.ingestion.injuries import run_injury_ingestion

log = structlog.get_logger()


async def run() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        counts = await run_injury_ingestion(session)
        session.commit()
        log.info("injury_ingestion_done", counts=counts)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
