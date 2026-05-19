import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import src.db.models  # noqa: F401


@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_: BigInteger, compiler: object, **kw: object) -> str:
    return "INTEGER"


from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.app import app
from src.api.deps import get_db
from src.db.base import Base

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(_engine)


def _override_get_db():
    with Session(_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def fresh_limiter():
    """Give each test a clean rate-limit counter."""
    original = app.state.limiter
    app.state.limiter = Limiter(key_func=get_remote_address)
    yield
    app.state.limiter = original


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ─── tests ────────────────────────────────────────────────────────────────────


def test_health_within_limit_returns_200(client) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_rate_limit_returns_429_after_60_requests(client) -> None:
    for _ in range(60):
        client.get("/api/health")
    resp = client.get("/api/health")
    assert resp.status_code == 429
