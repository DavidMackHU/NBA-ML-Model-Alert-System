import dataclasses
import datetime

from sqlalchemy.orm import Session

from src.db.models import Alert, Game
from src.edge.devig import MarketOdds


@dataclasses.dataclass
class EdgeResult:
    game_id: int
    market: str
    selection: str
    dk_price: int
    dk_fair_p: float
    pin_price: int
    pin_fair_p: float
    model_p: float
    ev_pct: float  # (model_p / dk_fair_p) - 1.0; raw decimal, not percentage
    edge_pin_vs_dk: float  # pin_fair_p - dk_fair_p


def _ev(model_p: float, dk_fair_p: float) -> float:
    return model_p / dk_fair_p - 1.0


def compute_edges(
    game_id: int,
    market: str,
    dk_odds: list[MarketOdds],
    pin_odds: list[MarketOdds],
    model_preds: dict[str, float],
    ev_threshold: float = 0.03,
) -> list[EdgeResult]:
    """Return EdgeResult for each selection where model EV vs DK exceeds ev_threshold
    and Pinnacle agrees that DK is underpricing the same side.

    Direction agreement: edge_pin_vs_dk > 0 (Pinnacle's fair price > DK's fair price
    for the same selection, meaning both sources see DK as cheap on that side).
    """
    dk_by_sel = {o.selection: o for o in dk_odds}
    pin_by_sel = {o.selection: o for o in pin_odds}

    results: list[EdgeResult] = []
    for selection, model_p in model_preds.items():
        dk = dk_by_sel.get(selection)
        pin = pin_by_sel.get(selection)
        if dk is None or pin is None:
            continue

        ev = _ev(model_p, dk.fair_prob)
        edge_pin_vs_dk = pin.fair_prob - dk.fair_prob

        if ev < ev_threshold:
            continue
        # ev > 0 implies model_p > dk_fair_p; require Pinnacle to agree direction
        if edge_pin_vs_dk <= 0:
            continue

        results.append(
            EdgeResult(
                game_id=game_id,
                market=market,
                selection=selection,
                dk_price=dk.price,
                dk_fair_p=dk.fair_prob,
                pin_price=pin.price,
                pin_fair_p=pin.fair_prob,
                model_p=model_p,
                ev_pct=ev,
                edge_pin_vs_dk=edge_pin_vs_dk,
            )
        )

    return results


def store_alert(
    session: Session,
    game: Game,
    edge: EdgeResult,
    as_of: datetime.datetime,
    prediction_id: int | None = None,
) -> Alert:
    """Persist an EdgeResult to the alerts table."""
    time_to_tip_seconds = max(0, int((game.tipoff_utc - as_of).total_seconds()))
    alert = Alert(
        game_id=edge.game_id,
        prediction_id=prediction_id,
        market=edge.market,
        selection=edge.selection,
        dk_price=edge.dk_price,
        dk_implied_p=round(edge.dk_fair_p, 6),
        pin_price=edge.pin_price,
        pin_implied_p=round(edge.pin_fair_p, 6),
        model_p=round(edge.model_p, 6),
        ev_pct=round(edge.ev_pct, 6),
        edge_pin_vs_dk=round(edge.edge_pin_vs_dk, 6),
        alert_time=as_of,
        time_to_tip_seconds=time_to_tip_seconds,
        shap_features_json=None,
        status="active",
        as_of=as_of,
    )
    session.add(alert)
    session.flush()
    return alert
