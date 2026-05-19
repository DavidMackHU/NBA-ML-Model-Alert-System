import dataclasses
import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import Game, Player
from src.features import odds_features, player_features, team_features
from src.ingestion.nba_stats import NBA_TEAM_NAMES

_FULL_TO_ABBR: dict[str, str] = {v: k for k, v in NBA_TEAM_NAMES.items()}


@dataclasses.dataclass
class GameFeatures:
    game_id: int
    as_of: datetime.datetime
    # Schedule context
    home_rest_days: int
    away_rest_days: int
    home_is_b2b: bool
    away_is_b2b: bool
    home_travel_km: float
    away_travel_km: float
    # Rolling team performance (last 10 completed games)
    home_rolling_pace: Optional[float]
    away_rolling_pace: Optional[float]
    home_rolling_ortg: Optional[float]
    away_rolling_ortg: Optional[float]
    home_rolling_drtg: Optional[float]
    away_rolling_drtg: Optional[float]
    # Injury-adjusted lineup strength
    home_usage_lost: float
    away_usage_lost: float
    # Line movement (24-hour window before as_of)
    dk_home_h2h_movement: Optional[float]
    pin_home_h2h_movement: Optional[float]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class PlayerGameFeatures:
    player_id: int
    game_id: int
    as_of: datetime.datetime
    rolling_usage: Optional[float]
    rolling_points: Optional[float]
    is_available: bool
    team_usage_lost: float

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def build_game_features(
    session: Session,
    game: Game,
    as_of: datetime.datetime,
) -> GameFeatures:
    home_abbr = _FULL_TO_ABBR.get(game.home_team, "")
    away_abbr = _FULL_TO_ABBR.get(game.away_team, "")
    date = game.date
    return GameFeatures(
        game_id=game.id,
        as_of=as_of,
        home_rest_days=team_features.rest_days(session, home_abbr, date, as_of),
        away_rest_days=team_features.rest_days(session, away_abbr, date, as_of),
        home_is_b2b=team_features.is_back_to_back(session, home_abbr, date, as_of),
        away_is_b2b=team_features.is_back_to_back(session, away_abbr, date, as_of),
        home_travel_km=team_features.travel_km_for_game(
            session, home_abbr, True, away_abbr, date, as_of
        ),
        away_travel_km=team_features.travel_km_for_game(
            session, away_abbr, False, home_abbr, date, as_of
        ),
        home_rolling_pace=team_features.rolling_pace(session, home_abbr, date, as_of),
        away_rolling_pace=team_features.rolling_pace(session, away_abbr, date, as_of),
        home_rolling_ortg=team_features.rolling_ortg(session, home_abbr, date, as_of),
        away_rolling_ortg=team_features.rolling_ortg(session, away_abbr, date, as_of),
        home_rolling_drtg=team_features.rolling_drtg(session, home_abbr, date, as_of),
        away_rolling_drtg=team_features.rolling_drtg(session, away_abbr, date, as_of),
        home_usage_lost=player_features.team_usage_lost(session, home_abbr, date, as_of),
        away_usage_lost=player_features.team_usage_lost(session, away_abbr, date, as_of),
        dk_home_h2h_movement=odds_features.line_movement(
            session, game.id, "draftkings", "h2h", game.home_team, as_of
        ),
        pin_home_h2h_movement=odds_features.line_movement(
            session, game.id, "pinnacle", "h2h", game.home_team, as_of
        ),
    )


def build_player_features(
    session: Session,
    player: Player,
    game: Game,
    as_of: datetime.datetime,
) -> PlayerGameFeatures:
    team_abbr = player.team_abbreviation or ""
    return PlayerGameFeatures(
        player_id=player.id,
        game_id=game.id,
        as_of=as_of,
        rolling_usage=player_features.rolling_usage(session, player.id, game.date, as_of),
        rolling_points=player_features.rolling_points(session, player.id, game.date, as_of),
        is_available=player_features.is_player_available(session, player.id, as_of),
        team_usage_lost=player_features.team_usage_lost(session, team_abbr, game.date, as_of),
    )
