import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.odds import (
    MARKETS,
    _parse_selection,
    run_odds_ingestion,
    store_snapshots,
)

NOW = datetime.datetime(2024, 1, 15, 20, 0, 0, tzinfo=datetime.timezone.utc)

SAMPLE_H2H_EVENT = {
    "id": "abc123",
    "commence_time": "2024-01-15T23:30:00Z",
    "home_team": "Boston Celtics",
    "away_team": "Los Angeles Lakers",
    "bookmakers": [
        {
            "key": "draftkings",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Boston Celtics", "price": -150},
                        {"name": "Los Angeles Lakers", "price": 130},
                    ],
                }
            ],
        },
        {
            "key": "pinnacle",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Boston Celtics", "price": -145},
                        {"name": "Los Angeles Lakers", "price": 125},
                    ],
                }
            ],
        },
    ],
}

SAMPLE_PROP_EVENT = {
    "id": "abc123",
    "commence_time": "2024-01-15T23:30:00Z",
    "home_team": "Boston Celtics",
    "away_team": "Los Angeles Lakers",
    "bookmakers": [
        {
            "key": "draftkings",
            "markets": [
                {
                    "key": "player_points",
                    "outcomes": [
                        {
                            "name": "Jayson Tatum",
                            "description": "Over",
                            "price": -115,
                            "point": 28.5,
                        },
                        {
                            "name": "Jayson Tatum",
                            "description": "Under",
                            "price": -105,
                            "point": 28.5,
                        },
                    ],
                }
            ],
        }
    ],
}


# --- pure function tests ---


def test_parse_selection_h2h_no_description() -> None:
    selection, line = _parse_selection({"name": "Boston Celtics", "price": -150})
    assert selection == "Boston Celtics"
    assert line is None


def test_parse_selection_prop_with_description() -> None:
    selection, line = _parse_selection(
        {"name": "Jayson Tatum", "description": "Over", "price": -115, "point": 28.5}
    )
    assert selection == "Jayson Tatum Over"
    assert line == 28.5


def test_parse_selection_truncates_at_100_chars() -> None:
    selection, _ = _parse_selection({"name": "X" * 200, "price": 100})
    assert len(selection) <= 100


def test_parse_selection_strips_whitespace_when_no_description() -> None:
    selection, _ = _parse_selection({"name": "  Team Name  ", "price": 100})
    assert selection == "Team Name"


# --- store_snapshots unit tests (mock DB session) ---


def _make_mock_session(game_id: int = 1) -> MagicMock:
    mock_game = MagicMock()
    mock_game.id = game_id
    session = MagicMock()
    return session, mock_game


def test_store_snapshots_h2h_two_books() -> None:
    session, mock_game = _make_mock_session()
    with patch("src.ingestion.odds._upsert_game", return_value=mock_game):
        count = store_snapshots(session, [SAMPLE_H2H_EVENT], "h2h", NOW)
    # 2 bookmakers × 2 outcomes each = 4 snapshots
    assert count == 4
    assert session.add.call_count == 4
    session.commit.assert_called_once()


def test_store_snapshots_props_one_book() -> None:
    session, mock_game = _make_mock_session()
    with patch("src.ingestion.odds._upsert_game", return_value=mock_game):
        count = store_snapshots(session, [SAMPLE_PROP_EVENT], "player_points", NOW)
    # 1 bookmaker × 2 outcomes (over + under)
    assert count == 2


def test_store_snapshots_skips_unknown_bookmaker() -> None:
    event = {
        **SAMPLE_H2H_EVENT,
        "bookmakers": [{"key": "fanduel", "markets": [{"key": "h2h", "outcomes": []}]}],
    }
    session, mock_game = _make_mock_session()
    with patch("src.ingestion.odds._upsert_game", return_value=mock_game):
        count = store_snapshots(session, [event], "h2h", NOW)
    assert count == 0


def test_store_snapshots_empty_events() -> None:
    session = MagicMock()
    count = store_snapshots(session, [], "h2h", NOW)
    assert count == 0
    session.add.assert_not_called()


# --- run_odds_ingestion guard ---


@pytest.mark.asyncio
async def test_run_ingestion_skips_when_no_api_key() -> None:
    session = MagicMock()
    with patch("src.ingestion.odds.get_settings") as mock_cfg:
        mock_cfg.return_value.odds_api_key = ""
        result = await run_odds_ingestion(session)
    assert result == {}
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_run_ingestion_calls_both_markets() -> None:
    session = MagicMock()
    with (
        patch("src.ingestion.odds.get_settings") as mock_cfg,
        patch("src.ingestion.odds.fetch_market", new_callable=AsyncMock) as mock_fetch,
        patch("src.ingestion.odds.store_snapshots", return_value=5) as mock_store,
    ):
        mock_cfg.return_value.odds_api_key = "test_key"
        mock_fetch.return_value = []
        result = await run_odds_ingestion(session)

    assert mock_fetch.call_count == len(MARKETS)
    assert mock_store.call_count == len(MARKETS)
    assert set(result.keys()) == set(MARKETS)
