import asyncio
import datetime
from typing import Any

import httpx
import structlog
from sqlalchemy.orm import Session

from src.db.models import Game, Player, PlayerGameStats, TeamGameStats

log = structlog.get_logger()

BASE_URL = "https://stats.nba.com/stats"
REQUEST_DELAY = 0.6  # seconds between calls — respect NBA Stats rate limit

NBA_STATS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Referer": "https://stats.nba.com/",
}

NBA_TEAM_NAMES: dict[str, str] = {
    "ATL": "Atlanta Hawks",
    "BOS": "Boston Celtics",
    "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors",
    "HOU": "Houston Rockets",
    "IND": "Indiana Pacers",
    "LAC": "LA Clippers",
    "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans",
    "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers",
    "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz",
    "WAS": "Washington Wizards",
}


async def _get(client: httpx.AsyncClient, endpoint: str, params: dict[str, Any]) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(3):
        try:
            resp = await client.get(url, params=params, headers=NBA_STATS_HEADERS, timeout=30.0)
            resp.raise_for_status()
            await asyncio.sleep(REQUEST_DELAY)
            return resp.json()
        except httpx.HTTPStatusError as exc:
            log.warning("nba_stats_http_error", status=exc.response.status_code, attempt=attempt)
            if exc.response.status_code in (403, 429) and attempt < 2:
                await asyncio.sleep(5 * (attempt + 1))
            elif attempt == 2:
                raise
        except httpx.TransportError:
            if attempt == 2:
                raise
            await asyncio.sleep(2**attempt)


def _rows_to_dicts(result_set: dict) -> list[dict]:
    return [dict(zip(result_set["headers"], row)) for row in result_set["rowSet"]]


def _parse_minutes(min_str: str | None) -> float | None:
    if not min_str:
        return None
    try:
        m, s = str(min_str).split(":")
        return float(m) + float(s) / 60
    except (ValueError, AttributeError):
        return None


def _find_result_set(data: dict, name: str) -> dict:
    empty: dict = {"headers": [], "rowSet": []}
    return next((rs for rs in data["resultSets"] if rs["name"] == name), empty)


async def fetch_scoreboard(client: httpx.AsyncClient, date: datetime.date) -> list[dict]:
    """Return [{nba_game_id, status_id, home_abbr, away_abbr}] for all games on date."""
    data = await _get(
        client,
        "scoreboardV2",
        {
            "GameDate": date.strftime("%m/%d/%Y"),
            "LeagueID": "00",
            "DayOffset": 0,
        },
    )
    games = _rows_to_dicts(_find_result_set(data, "GameHeader"))
    result = []
    for g in games:
        # GAMECODE: "20240115/BOSBKN" — date / away(3) + home(3)
        code = g.get("GAMECODE", "")
        teams_part = code.split("/")[1] if "/" in code else ""
        result.append(
            {
                "nba_game_id": g["GAME_ID"],
                "status_id": g.get("GAME_STATUS_ID", 0),
                "away_abbr": teams_part[:3] if len(teams_part) >= 6 else "",
                "home_abbr": teams_part[3:6] if len(teams_part) >= 6 else "",
            }
        )
    return result


async def fetch_box_score(client: httpx.AsyncClient, nba_game_id: str) -> dict:
    """Return traditional + advanced stats for all players and teams in a game."""
    box_params = {
        "GameID": nba_game_id,
        "StartPeriod": 0,
        "EndPeriod": 10,
        "StartRange": 0,
        "EndRange": 48000,
        "RangeType": 0,
    }
    trad = await _get(client, "boxscoretraditionalv2", box_params)
    adv = await _get(client, "boxscoreadvancedv2", box_params)
    return {
        "trad_players": _rows_to_dicts(_find_result_set(trad, "PlayerStats")),
        "trad_teams": _rows_to_dicts(_find_result_set(trad, "TeamStats")),
        "adv_players": _rows_to_dicts(_find_result_set(adv, "PlayerStats")),
        "adv_teams": _rows_to_dicts(_find_result_set(adv, "TeamStats")),
    }


def _find_or_create_game(
    session: Session,
    nba_game_id: str,
    date: datetime.date,
    home_abbr: str,
    away_abbr: str,
    as_of: datetime.datetime,
) -> Game:
    home_full = NBA_TEAM_NAMES.get(home_abbr, home_abbr)
    away_full = NBA_TEAM_NAMES.get(away_abbr, away_abbr)
    game = (
        session.query(Game)
        .filter(Game.date == date, Game.home_team == home_full, Game.away_team == away_full)
        .first()
    )
    if game is None:
        game = Game(
            game_id=nba_game_id,
            date=date,
            home_team=home_full,
            away_team=away_full,
            tipoff_utc=datetime.datetime.combine(
                date, datetime.time(0, 0), tzinfo=datetime.timezone.utc
            ),
            status="final",
            fetched_at=as_of,
            as_of=as_of,
        )
        session.add(game)
        session.flush()
    return game


def _upsert_player(session: Session, row: dict, as_of: datetime.datetime) -> Player:
    pid = str(row["PLAYER_ID"])
    player = session.query(Player).filter(Player.player_id == pid).first()
    if player is None:
        player = Player(
            player_id=pid,
            name=str(row.get("PLAYER_NAME", ""))[:100],
            team_abbreviation=str(row.get("TEAM_ABBREVIATION", ""))[:10],
            is_active=True,
            as_of=as_of,
        )
        session.add(player)
        session.flush()
    return player


def _store_player_stats(
    session: Session,
    game: Game,
    trad_rows: list[dict],
    adv_by_player_id: dict[str, dict],
    as_of: datetime.datetime,
) -> int:
    count = 0
    for row in trad_rows:
        if not row.get("MIN"):
            continue  # did not play
        player = _upsert_player(session, row, as_of)
        if (
            session.query(PlayerGameStats)
            .filter(PlayerGameStats.game_id == game.id, PlayerGameStats.player_id == player.id)
            .first()
        ):
            continue  # already stored
        adv = adv_by_player_id.get(str(row["PLAYER_ID"]), {})
        session.add(
            PlayerGameStats(
                game_id=game.id,
                player_id=player.id,
                minutes=_parse_minutes(row.get("MIN")),
                points=row.get("PTS"),
                rebounds=row.get("REB"),
                assists=row.get("AST"),
                steals=row.get("STL"),
                blocks=row.get("BLK"),
                turnovers=row.get("TO"),
                fg_attempted=row.get("FGA"),
                fg_made=row.get("FGM"),
                fg3_attempted=row.get("FG3A"),
                fg3_made=row.get("FG3M"),
                ft_attempted=row.get("FTA"),
                ft_made=row.get("FTM"),
                usage_pct=adv.get("USG_PCT"),
                plus_minus=row.get("PLUS_MINUS"),
                fetched_at=as_of,
                as_of=as_of,
            )
        )
        count += 1
    return count


def _store_team_stats(
    session: Session,
    game: Game,
    trad_teams: list[dict],
    adv_teams: list[dict],
    as_of: datetime.datetime,
) -> None:
    adv_by_abbr = {r.get("TEAM_ABBREVIATION", ""): r for r in adv_teams}
    for row in trad_teams:
        abbr = row.get("TEAM_ABBREVIATION", "")
        if (
            session.query(TeamGameStats)
            .filter(TeamGameStats.game_id == game.id, TeamGameStats.team_abbreviation == abbr)
            .first()
        ):
            continue
        is_home = NBA_TEAM_NAMES.get(abbr, abbr) == game.home_team
        adv = adv_by_abbr.get(abbr, {})
        session.add(
            TeamGameStats(
                game_id=game.id,
                team_abbreviation=abbr,
                is_home=is_home,
                pace=adv.get("PACE"),
                ortg=adv.get("OFF_RATING"),
                drtg=adv.get("DEF_RATING"),
                efg_pct=adv.get("EFG_PCT"),
                tov_pct=adv.get("TM_TOV_PCT"),
                orb_pct=adv.get("OREB_PCT"),
                ft_rate=None,
                fetched_at=as_of,
                as_of=as_of,
            )
        )
        pts = row.get("PTS")
        if pts is not None:
            if is_home:
                game.home_score = pts
            else:
                game.away_score = pts


async def run_stats_ingestion(
    session: Session,
    date: datetime.date | None = None,
) -> dict[str, Any]:
    """Fetch box scores for all final games on date (defaults to yesterday ET)."""
    if date is None:
        date = (datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=1)).date()
    as_of = datetime.datetime.now(tz=datetime.timezone.utc)
    summary: dict[str, Any] = {"date": str(date), "games": 0, "players": 0}

    async with httpx.AsyncClient() as client:
        scoreboard = await fetch_scoreboard(client, date)
        final_games = [g for g in scoreboard if g["status_id"] == 3]
        log.info("stats_ingestion_start", date=str(date), final_game_count=len(final_games))

        for entry in final_games:
            nba_game_id = entry["nba_game_id"]
            try:
                box = await fetch_box_score(client, nba_game_id)
            except Exception as exc:
                log.error("box_score_failed", game_id=nba_game_id, error=str(exc))
                continue

            game = _find_or_create_game(
                session,
                nba_game_id,
                date,
                entry["home_abbr"],
                entry["away_abbr"],
                as_of,
            )
            game.status = "final"
            game.as_of = as_of

            adv_by_pid = {str(r["PLAYER_ID"]): r for r in box["adv_players"]}
            n = _store_player_stats(session, game, box["trad_players"], adv_by_pid, as_of)
            _store_team_stats(session, game, box["trad_teams"], box["adv_teams"], as_of)
            session.commit()

            summary["games"] += 1
            summary["players"] += n
            log.info("game_stats_stored", nba_game_id=nba_game_id, players=n)

    return summary
