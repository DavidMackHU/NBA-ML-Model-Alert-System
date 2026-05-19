"""Every 30 min (9pm–2am ET): settle active alerts for completed games."""

import datetime

import structlog

from src.db.session import get_session_factory
from src.tracker.reconcile import reconcile_alerts

log = structlog.get_logger()


def main() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        as_of = datetime.datetime.utcnow()
        n = reconcile_alerts(session, as_of)
        log.info("reconciliation_done", alerts_settled=n)


if __name__ == "__main__":
    main()
