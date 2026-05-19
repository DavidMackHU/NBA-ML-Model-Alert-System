"""
Injury ingestion — Rotowire RSS and NBA official injury report.
Run every 30 min during active slate windows.
ingested_at records when WE saw the data; news_time is the source timestamp.
Only stores a new row when status changes for a player+source pair.
"""

import datetime
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import httpx
import structlog
from sqlalchemy.orm import Session

from src.db.models import Injury, Player
from src.ingestion.nba_stats import NBA_STATS_HEADERS

log = structlog.get_logger()

ROTOWIRE_RSS_URL = "https://www.rotowire.com/basketball/rss-player-news.php"
NBA_INJURY_URL = "https://stats.nba.com/stats/leagueinjurystatus"

_STATUS_KEYWORDS: dict[str, list[str]] = {
    "out": ["ruled out", " out ", "out for", "will not play", "won't play"],
    "doubtful": ["doubtful"],
    "questionable": ["questionable", "gtd", "game-time decision"],
    "probable": ["probable"],
    "available": ["available", "cleared", "will play", "off the injury report", "not on report"],
}

_NBA_STATUS_MAP: dict[str, str] = {
    "Out": "out",
    "Doubtful": "doubtful",
    "Questionable": "questionable",
    "GTD": "questionable",
    "Game Time Decision": "questionable",
    "Probable": "probable",
    "Available": "available",
    "Active": "available",
}


def classify_injury_status(text: str) -> str:
    lower = f" {text.lower()} "
    for status, keywords in _STATUS_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return status
    return "unknown"


def _parse_pub_date(date_str: str) -> datetime.datetime | None:
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def parse_rss_items(xml_text: str) -> list[dict]:
    """Parse Rotowire RSS XML → [{player_name, status, reason, pub_date}]."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("rss_parse_error", error=str(exc))
        return []

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date_str = (item.findtext("pubDate") or "").strip()

        # Rotowire titles: "LeBron James Ruled Out (Ankle)" — first 2 tokens = player name
        words = title.split()
        player_name = " ".join(words[:2]) if len(words) >= 2 else title

        items.append(
            {
                "player_name": player_name,
                "reason": title[:200],
                "status": classify_injury_status(f"{title} {description}"),
                "pub_date": _parse_pub_date(pub_date_str),
            }
        )
    return items


async def fetch_rotowire_rss(client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(ROTOWIRE_RSS_URL, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        return parse_rss_items(resp.text)
    except Exception as exc:
        log.warning("rotowire_rss_failed", error=str(exc))
        return []


async def fetch_nba_injury_report(client: httpx.AsyncClient, season: str = "2024-25") -> list[dict]:
    try:
        resp = await client.get(
            NBA_INJURY_URL,
            params={"LeagueID": "00", "Season": season},
            headers=NBA_STATS_HEADERS,
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
        rs = next(
            (r for r in data.get("resultSets", []) if r["name"] == "LeagueInjuryStatus"), None
        )
        if not rs:
            return []
        headers = rs["headers"]
        return [dict(zip(headers, row)) for row in rs["rowSet"]]
    except Exception as exc:
        log.warning("nba_injury_report_failed", error=str(exc))
        return []


def _find_player_by_name(session: Session, name: str) -> Player | None:
    return session.query(Player).filter(Player.name.ilike(name.strip())).first()


def _status_changed(session: Session, player_id: int, status: str, source: str) -> bool:
    """Return True if we should store — i.e., status differs from the most recent record."""
    recent = (
        session.query(Injury)
        .filter(Injury.player_id == player_id, Injury.source == source)
        .order_by(Injury.ingested_at.desc())
        .first()
    )
    return recent is None or recent.status != status


def store_rotowire_injuries(
    session: Session,
    items: list[dict],
    ingested_at: datetime.datetime,
) -> int:
    count = 0
    for item in items:
        if item["status"] == "unknown":
            continue
        player = _find_player_by_name(session, item["player_name"])
        if player is None:
            log.debug("rotowire_player_not_found", name=item["player_name"])
            continue
        if not _status_changed(session, player.id, item["status"], "rotowire"):
            continue
        session.add(
            Injury(
                player_id=player.id,
                status=item["status"],
                reason=item.get("reason"),
                source="rotowire",
                news_time=item.get("pub_date"),
                ingested_at=ingested_at,
                as_of=ingested_at,
            )
        )
        count += 1
    if count:
        session.commit()
    return count


def store_nba_injuries(
    session: Session,
    rows: list[dict],
    ingested_at: datetime.datetime,
) -> int:
    count = 0
    for row in rows:
        pid = str(row.get("PersonID", "")).strip()
        if not pid:
            continue
        player = session.query(Player).filter(Player.player_id == pid).first()
        if player is None:
            continue
        status = _NBA_STATUS_MAP.get(str(row.get("PlayerStatus", "")), "unknown")
        if status == "unknown":
            continue
        if not _status_changed(session, player.id, status, "nba_official"):
            continue
        reason = str(row.get("InjuryDescription", "")).strip()
        session.add(
            Injury(
                player_id=player.id,
                status=status,
                reason=reason[:200] if reason else None,
                source="nba_official",
                news_time=None,
                ingested_at=ingested_at,
                as_of=ingested_at,
            )
        )
        count += 1
    if count:
        session.commit()
    return count


async def run_injury_ingestion(session: Session, season: str = "2024-25") -> dict[str, int]:
    """Fetch both sources and persist status-change events. Safe to call every 30 min."""
    ingested_at = datetime.datetime.now(tz=datetime.timezone.utc)
    async with httpx.AsyncClient() as client:
        rss_items = await fetch_rotowire_rss(client)
        nba_rows = await fetch_nba_injury_report(client, season)
    rw = store_rotowire_injuries(session, rss_items, ingested_at)
    nba = store_nba_injuries(session, nba_rows, ingested_at)
    log.info("injury_ingestion_done", rotowire=rw, nba_official=nba)
    return {"rotowire": rw, "nba_official": nba}
