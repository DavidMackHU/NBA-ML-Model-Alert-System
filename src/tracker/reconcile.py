"""Post-game reconciliation — settle active alerts once their game is final.

For each active alert whose game is now final:
  1. Look up Pin closing odds (de-vigged fair prob at tipoff).
  2. Determine win/loss from the score.
  3. Compute CLV = pin_closing_fair_p - dk_implied_p.
  4. Write a BetsLog row and flip alert status to "settled".
"""

import datetime

from sqlalchemy.orm import Session

from src.db.models import Alert, BetsLog, Game
from src.edge.devig import latest_market_odds


def _h2h_outcome(game: Game, selection: str) -> str | None:
    """Return "win" or "loss" for a moneyline selection; None when scores unavailable."""
    if game.home_score is None or game.away_score is None:
        return None
    if selection == game.home_team:
        return "win" if game.home_score > game.away_score else "loss"
    if selection == game.away_team:
        return "win" if game.away_score > game.home_score else "loss"
    return None


def reconcile_alerts(session: Session, as_of: datetime.datetime) -> int:
    """Settle all active alerts whose games are final.

    Returns the count of alerts settled in this run.
    Safe to call repeatedly — alerts already settled are skipped via status filter,
    and an existing BetsLog row also prevents duplicate settlement.
    """
    pairs = (
        session.query(Alert, Game)
        .join(Game, Alert.game_id == Game.id)
        .filter(Alert.status == "active", Game.status == "final")
        .all()
    )

    settled = 0
    for alert, game in pairs:
        if session.query(BetsLog).filter_by(alert_id=alert.id).first():
            continue

        pin_closing = latest_market_odds(
            session, alert.game_id, "pinnacle", alert.market, game.tipoff_utc
        )
        pin_by_sel = {o.selection: o for o in pin_closing}
        pin_mo = pin_by_sel.get(alert.selection)

        outcome = _h2h_outcome(game, alert.selection) if alert.market == "h2h" else None

        if outcome is None and pin_mo is None:
            continue

        clv = (pin_mo.fair_prob - alert.dk_implied_p) if pin_mo else None

        session.add(
            BetsLog(
                alert_id=alert.id,
                outcome=outcome,
                pin_closing_price=pin_mo.price if pin_mo else None,
                pin_closing_implied_p=pin_mo.fair_prob if pin_mo else None,
                clv=clv,
                settled_at=as_of,
                as_of=as_of,
            )
        )
        alert.status = "settled"
        settled += 1

    session.commit()
    return settled
