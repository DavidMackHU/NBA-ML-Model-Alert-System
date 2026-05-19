from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel


class AlertSummary(BaseModel):
    id: uuid.UUID
    game_id: int
    market: str
    selection: str
    dk_price: int
    dk_implied_p: float
    pin_price: int
    pin_implied_p: float
    model_p: float
    ev_pct: float
    edge_pin_vs_dk: float
    alert_time: datetime.datetime
    time_to_tip_seconds: int
    status: str
    home_team: str
    away_team: str
    tipoff_utc: datetime.datetime


class ShapFeature(BaseModel):
    name: str
    value: float


class SimilarBet(BaseModel):
    alert_id: uuid.UUID
    game_date: datetime.date
    selection: str
    market: str
    ev_pct: float
    model_p: float
    dk_price: int
    outcome: str | None
    clv: float | None


class AlertDetail(AlertSummary):
    shap_features_json: dict[str, Any] | None = None
    shap_features: list[ShapFeature] = []
    similar_bets: list[SimilarBet] = []
    narrative: str | None = None


class LiveAlertsResponse(BaseModel):
    alerts: list[AlertSummary]
    count: int


class DailyCLV(BaseModel):
    date: str
    cumulative_clv: float
    cumulative_ev: float
    n_bets: int


class MarketBreakdown(BaseModel):
    market: str
    n_bets: int
    n_settled: int
    mean_clv: float
    mean_ev: float


class CLVResponse(BaseModel):
    days: int
    n_bets: int
    n_settled: int
    mean_clv: float
    mean_ev: float
    roi: float
    win_rate: float
    daily: list[DailyCLV] = []
    by_market: list[MarketBreakdown] = []


class BacktestFilters(BaseModel):
    season: int | None
    market: str
    threshold: float
    scenario: str


class EdgeBucket(BaseModel):
    label: str
    n_bets: int
    mean_clv: float


class CLVBucket(BaseModel):
    label: str
    count: int


class BacktestResponse(BaseModel):
    filters: BacktestFilters
    n_bets: int
    n_settled: int
    mean_clv: float
    mean_ev: float
    roi: float
    hit_rate: float
    brier_score: float
    edge_distribution: list[EdgeBucket] = []
    clv_distribution: list[CLVBucket] = []


class HealthResponse(BaseModel):
    status: str
    db: str


class BestEdge(BaseModel):
    alert_id: uuid.UUID
    market: str
    selection: str
    ev_pct: float
    model_p: float
    dk_implied_p: float
    pin_implied_p: float
    dk_price: int
    pin_price: int
    edge_pin_vs_dk: float
    alert_time: datetime.datetime


class TodayGame(BaseModel):
    game_id: int
    home_team: str
    away_team: str
    tipoff_utc: datetime.datetime
    tipoff_local_et: datetime.datetime
    status: str
    home_score: int | None
    away_score: int | None
    best_edge: BestEdge | None


class TodaySlateResponse(BaseModel):
    slate_date: datetime.date
    games: list[TodayGame]
    generated_at: datetime.datetime
