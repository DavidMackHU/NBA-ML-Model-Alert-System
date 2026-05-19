import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.injuries import (
    _NBA_STATUS_MAP,
    classify_injury_status,
    parse_rss_items,
    run_injury_ingestion,
    store_nba_injuries,
    store_rotowire_injuries,
)

NOW = datetime.datetime(2024, 1, 15, 20, 0, 0, tzinfo=datetime.timezone.utc)

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>RotoWire NBA Player News</title>
    <item>
      <title>LeBron James Ruled Out (Ankle)</title>
      <description>James will not play Thursday due to left ankle soreness.</description>
      <pubDate>Mon, 15 Jan 2024 18:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Jayson Tatum Questionable (Foot)</title>
      <description>Tatum is listed as questionable for tonight's game.</description>
      <pubDate>Mon, 15 Jan 2024 16:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Stephen Curry Available Off Injury Report</title>
      <description>Curry has been cleared and is off the injury report.</description>
      <pubDate>Mon, 15 Jan 2024 14:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

MALFORMED_RSS_XML = "this is not valid xml <<<"


# --- classify_injury_status ---


@pytest.mark.parametrize(
    "text,expected",
    [
        ("LeBron James Ruled Out (Ankle)", "out"),
        ("will not play tonight", "out"),
        ("Player is Doubtful to play", "doubtful"),
        ("Listed as Questionable", "questionable"),
        ("GTD with knee soreness", "questionable"),
        ("Player is Probable", "probable"),
        ("Available off injury report", "available"),
        ("Cleared to return", "available"),
        ("Scored 30 points last night", "unknown"),
    ],
)
def test_classify_injury_status(text: str, expected: str) -> None:
    assert classify_injury_status(text) == expected


# --- parse_rss_items ---


def test_parse_rss_items_returns_correct_count() -> None:
    items = parse_rss_items(SAMPLE_RSS_XML)
    assert len(items) == 3


def test_parse_rss_items_extracts_player_name() -> None:
    items = parse_rss_items(SAMPLE_RSS_XML)
    assert items[0]["player_name"] == "LeBron James"
    assert items[1]["player_name"] == "Jayson Tatum"


def test_parse_rss_items_classifies_status() -> None:
    items = parse_rss_items(SAMPLE_RSS_XML)
    assert items[0]["status"] == "out"
    assert items[1]["status"] == "questionable"
    assert items[2]["status"] == "available"


def test_parse_rss_items_parses_pub_date() -> None:
    items = parse_rss_items(SAMPLE_RSS_XML)
    assert items[0]["pub_date"] is not None
    assert items[0]["pub_date"].year == 2024


def test_parse_rss_items_handles_malformed_xml() -> None:
    items = parse_rss_items(MALFORMED_RSS_XML)
    assert items == []


def test_parse_rss_items_empty_feed() -> None:
    xml = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    assert parse_rss_items(xml) == []


# --- NBA status map ---


def test_nba_status_map_covers_expected_values() -> None:
    for key in ("Out", "Doubtful", "Questionable", "GTD", "Probable", "Available"):
        assert key in _NBA_STATUS_MAP
    assert _NBA_STATUS_MAP["Out"] == "out"
    assert _NBA_STATUS_MAP["GTD"] == "questionable"


# --- store_rotowire_injuries ---


def test_store_rotowire_skips_unknown_status() -> None:
    session = MagicMock()
    items = [{"player_name": "Random Person", "status": "unknown", "reason": "x", "pub_date": None}]
    count = store_rotowire_injuries(session, items, NOW)
    assert count == 0
    session.add.assert_not_called()


def test_store_rotowire_skips_unknown_player() -> None:
    session = MagicMock()
    items = [{"player_name": "Unknown Player", "status": "out", "reason": "x", "pub_date": None}]
    with patch("src.ingestion.injuries._find_player_by_name", return_value=None):
        count = store_rotowire_injuries(session, items, NOW)
    assert count == 0


def test_store_rotowire_stores_known_player_changed_status() -> None:
    session = MagicMock()
    mock_player = MagicMock()
    mock_player.id = 42
    items = [{"player_name": "LeBron James", "status": "out", "reason": "Ankle", "pub_date": NOW}]
    with (
        patch("src.ingestion.injuries._find_player_by_name", return_value=mock_player),
        patch("src.ingestion.injuries._status_changed", return_value=True),
    ):
        count = store_rotowire_injuries(session, items, NOW)
    assert count == 1
    session.add.assert_called_once()
    session.commit.assert_called_once()


def test_store_rotowire_skips_unchanged_status() -> None:
    session = MagicMock()
    mock_player = MagicMock()
    mock_player.id = 42
    items = [{"player_name": "LeBron James", "status": "out", "reason": "Ankle", "pub_date": NOW}]
    with (
        patch("src.ingestion.injuries._find_player_by_name", return_value=mock_player),
        patch("src.ingestion.injuries._status_changed", return_value=False),
    ):
        count = store_rotowire_injuries(session, items, NOW)
    assert count == 0
    session.add.assert_not_called()


# --- store_nba_injuries ---


def test_store_nba_injuries_maps_status_and_stores() -> None:
    session = MagicMock()
    mock_player = MagicMock()
    mock_player.id = 7
    session.query.return_value.filter.return_value.first.return_value = mock_player
    rows = [{"PersonID": "2544", "PlayerStatus": "Out", "InjuryDescription": "Left knee"}]
    with patch("src.ingestion.injuries._status_changed", return_value=True):
        count = store_nba_injuries(session, rows, NOW)
    assert count == 1


def test_store_nba_injuries_skips_missing_person_id() -> None:
    session = MagicMock()
    rows = [{"PersonID": "", "PlayerStatus": "Out", "InjuryDescription": "Knee"}]
    count = store_nba_injuries(session, rows, NOW)
    assert count == 0


# --- run_injury_ingestion ---


@pytest.mark.asyncio
async def test_run_injury_ingestion_returns_both_keys() -> None:
    session = MagicMock()
    with (
        patch("src.ingestion.injuries.fetch_rotowire_rss", new_callable=AsyncMock, return_value=[]),
        patch(
            "src.ingestion.injuries.fetch_nba_injury_report",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await run_injury_ingestion(session)
    assert "rotowire" in result
    assert "nba_official" in result
    assert result["rotowire"] == 0
    assert result["nba_official"] == 0
