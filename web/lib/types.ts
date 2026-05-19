export interface ShapFeature {
  name: string;
  value: number;
}

export interface SimilarBet {
  alert_id: string;
  game_date: string;
  selection: string;
  market: string;
  ev_pct: number;
  model_p: number;
  dk_price: number;
  outcome: string | null;
  clv: number | null;
}

export interface AlertDetail extends AlertSummary {
  shap_features_json: Record<string, number> | null;
  shap_features: ShapFeature[];
  similar_bets: SimilarBet[];
  narrative: string | null;
}

export interface EdgeBucket {
  label: string;
  n_bets: number;
  mean_clv: number;
}

export interface CLVBucket {
  label: string;
  count: number;
}

export interface BacktestFilters {
  season: number | null;
  market: string;
  threshold: number;
  scenario: string;
}

export interface BacktestResponse {
  filters: BacktestFilters;
  n_bets: number;
  n_settled: number;
  mean_clv: number;
  mean_ev: number;
  roi: number;
  hit_rate: number;
  brier_score: number;
  edge_distribution: EdgeBucket[];
  clv_distribution: CLVBucket[];
}

export interface DailyCLV {
  date: string;
  cumulative_clv: number;
  cumulative_ev: number;
  n_bets: number;
}

export interface MarketBreakdown {
  market: string;
  n_bets: number;
  n_settled: number;
  mean_clv: number;
  mean_ev: number;
}

export interface CLVResponse {
  days: number;
  n_bets: number;
  n_settled: number;
  mean_clv: number;
  mean_ev: number;
  roi: number;
  win_rate: number;
  daily: DailyCLV[];
  by_market: MarketBreakdown[];
}

export interface AlertSummary {
  id: string;
  game_id: number;
  market: string;
  selection: string;
  dk_price: number;
  dk_implied_p: number;
  pin_price: number;
  pin_implied_p: number;
  model_p: number;
  ev_pct: number;
  edge_pin_vs_dk: number;
  alert_time: string;
  time_to_tip_seconds: number;
  status: string;
  home_team: string;
  away_team: string;
  tipoff_utc: string;
}
