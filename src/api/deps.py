from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        from src.config.settings import Settings

        _engine = create_engine(Settings().database_url)
    return _engine


def get_db() -> Generator[Session, None, None]:
    with Session(_get_engine()) as session:
        yield session
