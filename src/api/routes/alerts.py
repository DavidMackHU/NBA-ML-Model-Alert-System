import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.limiter import limiter
from src.api.schemas import AlertDetail, AlertSummary, LiveAlertsResponse, ShapFeature, SimilarBet
from src.db.models import Alert, BetsLog, Game

router = APIRouter()

_LIVE_WINDOW_HOURS = 6
_SHAP_TOP_N = 10
_SIMILAR_LIMIT = 5


def _build_summary(alert: Alert, game: Game) -> AlertSummary:
    return AlertSummary(
        id=alert.id,
        game_id=alert.game_id,
        market=alert.market,
        selection=alert.selection,
        dk_price=alert.dk_price,
        dk_implied_p=alert.dk_implied_p,
        pin_price=alert.pin_price,
        pin_implied_p=alert.pin_implied_p,
        model_p=alert.model_p,
        ev_pct=alert.ev_pct,
        edge_pin_vs_dk=alert.edge_pin_vs_dk,
        alert_time=alert.alert_time,
        time_to_tip_seconds=alert.time_to_tip_seconds,
        status=alert.status,
        home_team=game.home_team,
        away_team=game.away_team,
        tipoff_utc=game.tipoff_utc,
    )


def _parse_shap(shap_json: dict | None) -> list[ShapFeature]:
    if not shap_json:
        return []
    ranked = sorted(shap_json.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return [ShapFeature(name=k, value=v) for k, v in ranked[:_SHAP_TOP_N]]


def _build_narrative(alert: Alert) -> str:
    market_label = "moneyline" if alert.market == "h2h" else "player points"
    ev_str = f"{alert.ev_pct * 100:+.1f}%"
    pin_pct = f"{alert.pin_implied_p * 100:.1f}%"
    dk_pct = f"{alert.dk_implied_p * 100:.1f}%"
    gap_pp = f"{alert.edge_pin_vs_dk * 100:+.1f}pp"
    model_pct = f"{alert.model_p * 100:.1f}%"
    return (
        f"{alert.selection} was flagged as a {market_label} candidate with a "
        f"{ev_str} modeled edge. Pinnacle implied {pin_pct} probability while "
        f"DraftKings offered {dk_pct} — a {gap_pp} gap using Pinnacle as the sharp "
        f"reference. The model estimated {model_pct} win probability."
    )


def _find_similar(session: Session, alert: Alert) -> list[SimilarBet]:
    rows = (
        session.query(Alert, BetsLog, Game)
        .join(BetsLog, BetsLog.alert_id == Alert.id)
        .join(Game, Alert.game_id == Game.id)
        .filter(Alert.market == alert.market, Alert.id != alert.id)
        .order_by(Alert.alert_time.desc())
        .limit(_SIMILAR_LIMIT)
        .all()
    )
    return [
        SimilarBet(
            alert_id=a.id,
            game_date=g.date,
            selection=a.selection,
            market=a.market,
            ev_pct=a.ev_pct,
            model_p=a.model_p,
            dk_price=a.dk_price,
            outcome=b.outcome,
            clv=b.clv,
        )
        for a, b, g in rows
    ]


@router.get("/alerts/live", response_model=LiveAlertsResponse)
@limiter.limit("60/minute")
def get_live_alerts(request: Request, db: Session = Depends(get_db)) -> LiveAlertsResponse:
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=_LIVE_WINDOW_HOURS)
    rows = (
        db.query(Alert, Game)
        .join(Game, Alert.game_id == Game.id)
        .filter(Alert.status == "active", Alert.alert_time >= cutoff)
        .order_by(Alert.alert_time.desc())
        .all()
    )
    summaries = [_build_summary(a, g) for a, g in rows]
    return LiveAlertsResponse(alerts=summaries, count=len(summaries))


@router.get("/alerts/{alert_id}", response_model=AlertDetail)
@limiter.limit("60/minute")
def get_alert(request: Request, alert_id: uuid.UUID, db: Session = Depends(get_db)) -> AlertDetail:
    row = (
        db.query(Alert, Game)
        .join(Game, Alert.game_id == Game.id)
        .filter(Alert.id == alert_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert, game = row
    summary = _build_summary(alert, game)
    return AlertDetail(
        **summary.model_dump(),
        shap_features_json=alert.shap_features_json,
        shap_features=_parse_shap(alert.shap_features_json),
        similar_bets=_find_similar(db, alert),
        narrative=_build_narrative(alert),
    )
