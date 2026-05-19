import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.nba_stats import (
    NBA_TEAM_NAMES,
    _find_or_create_game,
    _parse_minutes,
    _rows_to_dicts,
    _store_player_stats,
    fetch_scoreboard,
    run_stats_ingestion,
)

NOW = datetime.datetime(2024, 1, 15, 22, 0, 0, tzinfo=datetime.timezone.utc)
DATE = datetime.date(2024, 1, 15)


# --- pure function tests ---


def test_parse_minutes_normal() -> None:
    assert abs(_parse_minutes("35:23") - 35.383) < 0.01


def test_parse_minutes_zero() -> None:
    assert _parse_minutes("00:00") == 0.0


def test_parse_minutes_none() -> None:
    assert _parse_minutes(None) is None


def test_parse_minutes_empty_string() -> None:
    assert _parse_minutes("") is None


def test_rows_to_dicts() -> None:
    rs = {"headers": ["A", "B", "C"], "rowSet": [[1, 2, 3], [4, 5, 6]]}
    result = _rows_to_dicts(rs)
    assert result == [{"A": 1, "B": 2, "C": 3}, {"A": 4, "B": 5, "C": 6}]


def test_rows_to_dicts_empty() -> None:
    rs = {"headers": ["A", "B"], "rowSet": []}
    assert _rows_to_dicts(rs) == []


def test_nba_team_names_has_all_30_teams() -> None:
    assert len(NBA_TEAM_NAMES) == 30


def test_nba_team_names_known_entries() -> None:
    assert NBA_TEAM_NAMES["BOS"] == "Boston Celtics"
    assert NBA_TEAM_NAMES["LAL"] == "Los Angeles Lakers"
    assert NBA_TEAM_NAMES["GSW"] == "Golden State Warriors"


# --- fetch_scoreboard parsing ---


@pytest.mark.asyncio
async def test_fetch_scoreboard_parses_gamecode() -> None:
    mock_response = {
        "resultSets": [
            {
                "name": "GameHeader",
                "headers": ["GAME_ID", "GAME_STATUS_ID", "GAMECODE"],
                "rowSet": [
                    ["0022300001", 3, "20240115/BOSBKN"],
                    ["0022300002", 1, "20240115/LALGWS"],
                ],
            }
        ]
    }
    mock_client = MagicMock()
    with patch("src.ingestion.nba_stats._get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await fetch_scoreboard(mock_client, DATE)

    assert len(result) == 2
    assert result[0] == {
        "nba_game_id": "0022300001",
        "status_id": 3,
        "away_abbr": "BOS",
        "home_abbr": "BKN",
    }
    assert result[1]["status_id"] == 1
    assert result[1]["home_abbr"] == "GWS"  # raw parse — not a real team but tests parsing


# --- _find_or_create_game ---


def test_find_game_returns_existing() -> None:
    existing = MagicMock()
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = existing
    game = _find_or_create_game(session, "nba123", DATE, "BOS", "NYK", NOW)
    assert game is existing
    session.add.assert_not_called()


def test_find_game_creates_when_missing() -> None:
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    game = _find_or_create_game(session, "nba123", DATE, "BOS", "NYK", NOW)
    session.add.assert_called_once()
    assert game.home_team == "Boston Celtics"
    assert game.away_team == "New York Knicks"


# --- _store_player_stats ---


def test_store_player_stats_skips_no_minutes() -> None:
    session = MagicMock()
    game = MagicMock()
    game.id = 1
    rows = [{"PLAYER_ID": 123, "PLAYER_NAME": "Player A", "TEAM_ABBREVIATION": "BOS", "MIN": None}]
    count = _store_player_stats(session, game, rows, {}, NOW)
    assert count == 0
    session.add.assert_not_called()


def test_store_player_stats_stores_valid_row() -> None:
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    game = MagicMock()
    game.id = 1

    mock_player = MagicMock()
    mock_player.id = 99
    trad_rows = [
        {
            "PLAYER_ID": 2544,
            "PLAYER_NAME": "LeBron James",
            "TEAM_ABBREVIATION": "LAL",
            "MIN": "35:23",
            "PTS": 28,
            "REB": 7,
            "AST": 9,
            "STL": 1,
            "BLK": 0,
            "TO": 3,
            "FGM": 11,
            "FGA": 18,
            "FG3M": 2,
            "FG3A": 5,
            "FTM": 4,
            "FTA": 4,
            "PLUS_MINUS": 8,
        }
    ]
    adv_by_id = {"2544": {"USG_PCT": 0.31}}

    with patch("src.ingestion.nba_stats._upsert_player", return_value=mock_player):
        count = _store_player_stats(session, game, trad_rows, adv_by_id, NOW)

    assert count == 1
    session.add.assert_called_once()


# --- run_stats_ingestion ---


@pytest.mark.asyncio
async def test_run_stats_ingestion_no_final_games() -> None:
    session = MagicMock()
    scoreboard = [{"nba_game_id": "001", "status_id": 1, "home_abbr": "BOS", "away_abbr": "NYK"}]
    with (
        patch("src.ingestion.nba_stats.fetch_scoreboard", new_callable=AsyncMock) as mock_sb,
        patch("src.ingestion.nba_stats.fetch_box_score", new_callable=AsyncMock) as mock_box,
    ):
        mock_sb.return_value = scoreboard
        result = await run_stats_ingestion(session, date=DATE)

    mock_box.assert_not_called()
    assert result["games"] == 0
