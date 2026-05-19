import datetime

from sqlalchemy.orm import Session

from src.db.models import Game
from src.ingestion.nba_stats import NBA_TEAM_NAMES

_FULL_TO_ABBR: dict[str, str] = {v: k for k, v in NBA_TEAM_NAMES.items()}

INITIAL_ELO: float = 1500.0
K_FACTOR: float = 20.0
HOME_ADVANTAGE: float = 100.0  # Elo points added to the home team's effective rating


def expected_win_prob(rating_a: float, rating_b: float) -> float:
    """P(A beats B) via the standard Elo formula."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_ratings(
    winner_rating: float,
    loser_rating: float,
    k: float = K_FACTOR,
) -> tuple[float, float]:
    """Return (new_winner_elo, new_loser_elo) after one game."""
    p_winner = expected_win_prob(winner_rating, loser_rating)
    delta = k * (1.0 - p_winner)
    return winner_rating + delta, loser_rating - delta


def build_team_elos(
    session: Session,
    as_of: datetime.datetime,
    k: float = K_FACTOR,
) -> dict[str, float]:
    """Return point-in-time Elo ratings for all teams.

    Only games with status='final' and date < as_of.date() are processed,
    in chronological order.  Teams without history start at INITIAL_ELO.
    """
    cutoff = as_of.date()
    games = (
        session.query(Game)
        .filter(
            Game.status == "final",
            Game.date < cutoff,
            Game.home_score.isnot(None),
            Game.away_score.isnot(None),
        )
        .order_by(Game.date.asc())
        .all()
    )

    elos: dict[str, float] = {}
    for game in games:
        home_abbr = _FULL_TO_ABBR.get(game.home_team, "")
        away_abbr = _FULL_TO_ABBR.get(game.away_team, "")
        if not home_abbr or not away_abbr:
            continue
        home_elo = elos.get(home_abbr, INITIAL_ELO)
        away_elo = elos.get(away_abbr, INITIAL_ELO)
        if game.home_score > game.away_score:
            new_home, new_away = update_ratings(home_elo, away_elo, k)
        elif game.away_score > game.home_score:
            new_away, new_home = update_ratings(away_elo, home_elo, k)
        else:
            continue  # ties don't occur in NBA regulation
        elos[home_abbr] = new_home
        elos[away_abbr] = new_away

    return elos


def home_win_prob(
    home_abbr: str,
    away_abbr: str,
    elos: dict[str, float],
    home_advantage: float = HOME_ADVANTAGE,
) -> float:
    """Modeled P(home wins).

    Home-court advantage is applied as an Elo offset before computing
    win probability — a standard approach that adds ~3-4 percentage points
    to the home team's implied probability at equal ratings.
    """
    home_elo = elos.get(home_abbr, INITIAL_ELO) + home_advantage
    away_elo = elos.get(away_abbr, INITIAL_ELO)
    return expected_win_prob(home_elo, away_elo)
