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


from src.api.app import app
from src.api.deps import get_db
from src.db.base import Base


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


# ─── /api/backtest ────────────────────────────────────────────────────────────


def test_backtest_returns_200_with_empty_data(client: TestClient) -> None:
    resp = client.get("/api/backtest?season=2024&market=h2h&threshold=0.03&scenario=perfect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["n_bets"] == 0
    assert data["n_settled"] == 0


def test_backtest_invalid_scenario_returns_400(client: TestClient) -> None:
    resp = client.get("/api/backtest?scenario=bogus")
    assert resp.status_code == 400


def test_backtest_default_params(client: TestClient) -> None:
    data = client.get("/api/backtest").json()
    assert data["filters"]["market"] == "h2h"
    assert data["filters"]["threshold"] == 0.03
    assert data["filters"]["scenario"] == "perfect"
    assert data["filters"]["season"] is None


def test_backtest_schema_complete(client: TestClient) -> None:
    data = client.get("/api/backtest").json()
    for field in ("n_bets", "n_settled", "mean_clv", "mean_ev", "roi", "hit_rate", "brier_score"):
        assert field in data


def test_backtest_has_distribution_fields(client: TestClient) -> None:
    data = client.get("/api/backtest").json()
    assert "edge_distribution" in data
    assert "clv_distribution" in data
    assert isinstance(data["edge_distribution"], list)
    assert isinstance(data["clv_distribution"], list)


def test_backtest_distribution_bucket_structure(client: TestClient) -> None:
    data = client.get("/api/backtest").json()
    assert len(data["edge_distribution"]) == 4
    for bucket in data["edge_distribution"]:
        assert "label" in bucket
        assert "n_bets" in bucket
        assert "mean_clv" in bucket
    assert len(data["clv_distribution"]) == 4
    for bucket in data["clv_distribution"]:
        assert "label" in bucket
        assert "count" in bucket
