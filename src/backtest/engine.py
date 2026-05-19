import dataclasses
import datetime
import enum

from sqlalchemy.orm import Session

from src.db.models import Game, ModelPrediction
from src.edge.devig import latest_market_odds
from src.edge.ev import compute_edges


@dataclasses.dataclass
class BacktestBet:
    game_id: int
    market: str
    selection: str
    dk_price: int  # American odds at alert time (used for P&L)
    dk_fair_p: float  # de-vigged DK fair prob at alert time (used for CLV)
    pin_fair_p: float  # de-vigged Pin fair prob at alert time
    pin_closing_fair_p: float  # de-vigged Pin fair prob at close (CLV target)
    model_p: float
    ev_pct: float
    outcome: int | None  # 1=won, 0=lost, None=unsettled
    game_date: datetime.date


@dataclasses.dataclass
class ScenarioResult:
    n_bets: int
    n_settled: int
    mean_clv: float  # mean(pin_closing_fair_p - dk_fair_p); positive = beat close
    mean_ev: float  # mean ev_pct at alert time
    roi: float  # sum(pnl) / n_settled for $1 flat bets
    hit_rate: float  # fraction of settled bets that won
    brier_score: float  # mean((model_p - outcome)^2)


class Scenario(enum.Enum):
    PERFECT = "perfect"
    TICK_WORSE = "tick_worse"
    UNAVAILABLE_20PCT = "unavailable_20pct"
    LIMIT_AFTER_200 = "limit_after_200"


def clv_of(dk_fair_p: float, pin_closing_fair_p: float) -> float:
    """CLV in probability terms: positive means you beat the closing price."""
    return pin_closing_fair_p - dk_fair_p


def pnl_flat(dk_price: int, outcome: int) -> float:
    """P&L for a $1 flat bet at the given American odds."""
    if outcome == 1:
        return dk_price / 100.0 if dk_price > 0 else 100.0 / abs(dk_price)
    return -1.0


def apply_scenario(bets: list[BacktestBet], scenario: Scenario) -> list[BacktestBet]:
    """Transform a bet list to reflect real-world execution constraints.

    TICK_WORSE: models paying ~5 cents more vig by raising dk_fair_p 0.5pp.
    UNAVAILABLE_20PCT: every 5th bet (by position) is unavailable — deterministic.
    LIMIT_AFTER_200: DK limits accounts to uneconomical sizes after ~200 bets;
        keep only the first 200.
    """
    if scenario == Scenario.PERFECT:
        return list(bets)
    if scenario == Scenario.TICK_WORSE:
        return [dataclasses.replace(b, dk_fair_p=b.dk_fair_p + 0.005) for b in bets]
    if scenario == Scenario.UNAVAILABLE_20PCT:
        return [b for i, b in enumerate(bets) if i % 5 != 0]
    if scenario == Scenario.LIMIT_AFTER_200:
        return bets[:200]
    return list(bets)


def aggregate(bets: list[BacktestBet]) -> ScenarioResult:
    """Compute CLV, ROI, hit rate, and Brier score over a bet list."""
    settled = [b for b in bets if b.outcome is not None]
    if not settled:
        return ScenarioResult(
            n_bets=len(bets),
            n_settled=0,
            mean_clv=0.0,
            mean_ev=0.0,
            roi=0.0,
            hit_rate=0.0,
            brier_score=0.0,
        )
    n = len(settled)
    clv_vals = [clv_of(b.dk_fair_p, b.pin_closing_fair_p) for b in settled]
    pnl_vals = [pnl_flat(b.dk_price, b.outcome) for b in settled]
    brier = sum((b.model_p - b.outcome) ** 2 for b in settled) / n
    return ScenarioResult(
        n_bets=len(bets),
        n_settled=n,
        mean_clv=sum(clv_vals) / n,
        mean_ev=sum(b.ev_pct for b in settled) / n,
        roi=sum(pnl_vals) / n,
        hit_rate=sum(b.outcome for b in settled) / n,
        brier_score=brier,
    )


def _game_outcome_h2h(game: Game) -> dict[str, int]:
    """Return {selection: 1/0} for h2h market. Empty dict when score unavailable."""
    if game.home_score is None or game.away_score is None:
        return {}
    home_win = int(game.home_score > game.away_score)
    return {game.home_team: home_win, game.away_team: 1 - home_win}


def collect_bets(
    session: Session,
    start_date: datetime.date,
    end_date: datetime.date,
    ev_threshold: float,
    market: str,
) -> list[BacktestBet]:
    """Replay alert-firing logic on historical data, returning simulated bets."""
    games = (
        session.query(Game)
        .filter(
            Game.status == "final",
            Game.date >= start_date,
            Game.date < end_date,
        )
        .order_by(Game.date)
        .all()
    )

    bets: list[BacktestBet] = []
    for game in games:
        as_of = game.tipoff_utc - datetime.timedelta(hours=1)

        preds = (
            session.query(ModelPrediction)
            .filter(
                ModelPrediction.game_id == game.id,
                ModelPrediction.market == market,
                ModelPrediction.as_of <= as_of,
            )
            .all()
        )
        if not preds:
            continue
        model_preds = {p.selection: p.model_p for p in preds}

        dk_odds = latest_market_odds(session, game.id, "draftkings", market, as_of)
        pin_odds = latest_market_odds(session, game.id, "pinnacle", market, as_of)
        if not dk_odds or not pin_odds:
            continue

        pin_closing = latest_market_odds(session, game.id, "pinnacle", market, game.tipoff_utc)
        if not pin_closing:
            continue
        pin_close_by_sel = {o.selection: o.fair_prob for o in pin_closing}

        edges = compute_edges(game.id, market, dk_odds, pin_odds, model_preds, ev_threshold)
        outcome_map = _game_outcome_h2h(game) if market == "h2h" else {}

        for edge in edges:
            pin_close_p = pin_close_by_sel.get(edge.selection)
            if pin_close_p is None:
                continue
            bets.append(
                BacktestBet(
                    game_id=game.id,
                    market=market,
                    selection=edge.selection,
                    dk_price=edge.dk_price,
                    dk_fair_p=edge.dk_fair_p,
                    pin_fair_p=edge.pin_fair_p,
                    pin_closing_fair_p=pin_close_p,
                    model_p=edge.model_p,
                    ev_pct=edge.ev_pct,
                    outcome=outcome_map.get(edge.selection),
                    game_date=game.date,
                )
            )

    return bets


def run_backtest(
    session: Session,
    start_date: datetime.date,
    end_date: datetime.date,
    ev_threshold: float = 0.03,
    market: str = "h2h",
) -> dict[Scenario, ScenarioResult]:
    """Walk-forward backtest over a date range.

    Returns one ScenarioResult per Scenario so callers can compare execution
    assumptions side-by-side. CLV is the primary metric; ROI is secondary.
    """
    bets = collect_bets(session, start_date, end_date, ev_threshold, market)
    return {s: aggregate(apply_scenario(bets, s)) for s in Scenario}


_EDGE_DEFS = [
    ("1–3%", 0.01, 0.03),
    ("3–5%", 0.03, 0.05),
    ("5–8%", 0.05, 0.08),
    ("8%+", 0.08, float("inf")),
]

_CLV_DEFS = [
    ("< -3%", float("-inf"), -0.03),
    ("-3 to 0%", -0.03, 0.0),
    ("0 to 3%", 0.0, 0.03),
    ("3%+", 0.03, float("inf")),
]


def compute_distributions(
    bets: list[BacktestBet],
) -> tuple[list[dict], list[dict]]:
    """Bucket bets by edge size and CLV outcome for chart display."""
    edge_data: dict[str, dict] = {
        label: {"n_bets": 0, "clv_sum": 0.0, "n_settled": 0} for label, _, _ in _EDGE_DEFS
    }
    clv_counts: dict[str, int] = {label: 0 for label, _, _ in _CLV_DEFS}

    for b in bets:
        for label, lo, hi in _EDGE_DEFS:
            if lo <= b.ev_pct < hi:
                edge_data[label]["n_bets"] += 1
                if b.outcome is not None:
                    edge_data[label]["clv_sum"] += clv_of(b.dk_fair_p, b.pin_closing_fair_p)
                    edge_data[label]["n_settled"] += 1
                break

        if b.outcome is not None:
            c = clv_of(b.dk_fair_p, b.pin_closing_fair_p)
            for label, lo, hi in _CLV_DEFS:
                if lo <= c < hi:
                    clv_counts[label] += 1
                    break

    edge_dist = [
        {
            "label": label,
            "n_bets": edge_data[label]["n_bets"],
            "mean_clv": (
                edge_data[label]["clv_sum"] / edge_data[label]["n_settled"]
                if edge_data[label]["n_settled"] > 0
                else 0.0
            ),
        }
        for label, _, _ in _EDGE_DEFS
    ]
    clv_dist = [{"label": label, "count": clv_counts[label]} for label, _, _ in _CLV_DEFS]
    return edge_dist, clv_dist
