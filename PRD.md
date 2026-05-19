# NBA +EV Alert System — Product Requirements Document

## 1. Overview

A full-stack ML application: a data pipeline + ML models + FastAPI backend + Next.js mobile-first public web dashboard + private Telegram alerts. Ingests live NBA odds, player and team stats, and injury news; predicts moneyline outcomes and player points distributions; benchmarks DraftKings prices against Pinnacle as the sharp market reference; sends private Telegram alerts to the developer when EV thresholds are met; surfaces all live alerts, CLV tracking, backtest results, and model explanations on a public mobile-friendly dashboard. Backtested with walk-forward validation and point-in-time data integrity, with closing line value (CLV) against Pinnacle as the primary success metric.

This is a portfolio project. The deliverables are: a working system, a deployed public dashboard, rigorous backtests, and an honest writeup — not a live betting operation.

## 2. Problem Framing

Sports betting markets are competitive and reflexive. Apparent +EV opportunities against a recreational-leaning book (DraftKings) typically come from:

1. The book hasn't yet absorbed information the sharp market has (line lag)
2. Public bias on popular teams, primetime games, or star players
3. Slower line movement on less-trafficked markets like player props

Pinnacle is widely treated as the sharp reference because it accepts large bets without limiting winners. When DraftKings' implied probability diverges meaningfully from Pinnacle's, that gap is a candidate edge — but only a candidate. In practice, sustainable exploitation is constrained by account limits, line availability, and execution latency. The honest portfolio version of this project measures the apparent edge, then quantifies how much survives realistic execution assumptions, and surfaces all of it transparently in a public dashboard.

## 3. Goals & Non-Goals

### Goals

- End-to-end pipeline: ingestion → features → modeling → edge detection → alerting → backtest → live tracking
- Public, mobile-friendly web dashboard recruiters can click through on phone or desktop
- Point-in-time data discipline and walk-forward validation throughout
- Portfolio README that an ML/quant hiring manager respects
- Run live for ≥30 days post-launch and publish live CLV vs backtest CLV

### Non-Goals (v1)

- Not a betting product. No automated wagering, no real money.
- No claims of profitability. Dashboard's About page discusses why apparent edges shrink.
- No user authentication. Read-only public dashboard with rate limiting.
- NBA only, moneyline + player points props only.

## 4. Tech Stack

### Pipeline & Backend

- Python 3.11+, uv package manager
- pandas / numpy / scipy
- scikit-learn, xgboost, statsmodels, shap
- FastAPI + uvicorn, sse-starlette, slowapi
- SQLAlchemy 2.x + Alembic
- Postgres (Supabase free tier; local Postgres dev)
- httpx, python-telegram-bot
- pydantic-settings, structlog
- pytest + pytest-asyncio

### Frontend

- Next.js 14 (App Router)
- TypeScript strict mode
- Tailwind CSS (mobile-first)
- shadcn/ui (Radix + Tailwind, copy-paste components)
- Recharts (charts)
- TanStack Query + native EventSource (data + live stream)
- lucide-react (icons)

### Infrastructure

- Render (backend web service + cron jobs)
- Vercel (frontend + keepalive cron)
- Supabase (Postgres)
- GitHub Actions (pipeline schedulers + CI)
- Docker + docker-compose (local dev)

**Total: $0/month**

## 5. Core Features

### 5.1 Data Ingestion

- **Odds (The Odds API):** DK + Pinnacle, h2h + player_points. Hourly during slate windows. Full snapshot history retained.
- **Stats (NBA Stats API):** Daily post-slate. Box scores, advanced stats, rotations.
- **Injuries (Rotowire RSS + NBA official injury report PDF):** Every 30 min during the day. `ingested_at` is the join key, not article time.

### 5.2 Feature Engineering

Point-in-time enforced via `as_of` on every join. Rest, travel, team strength (Elo, OffRtg, DefRtg), player usage/minutes, opponent DRtg vs position, line movement, injury-adjusted lineup strength.

### 5.3 Models

- **Moneyline:** XGBoost classifier with isotonic calibration. Elo baseline.
- **Player points:** XGBoost mean + log-variance with negative binomial, OR XGBoost quantile regression. Rolling-average baseline.
- Walk-forward CV. Weekly refit in production.

### 5.4 De-vig & Edge Detection

- De-vig DK and Pinnacle via power method
- Track three edges: model-vs-DK, Pinnacle-vs-DK, model-vs-Pinnacle
- Alert when (model-vs-DK) > threshold AND sign matches (Pinnacle-vs-DK)
- Threshold configurable, default 3% EV

### 5.5 Backtesting

- Walk-forward, point-in-time, CLV-primary
- 4 execution-realism scenarios: perfect / 1-tick worse / 20% unavailable / $100 limit after 200 bets
- Report all four. Honest analysis of which produce positive CLV.

### 5.6 Telegram Alerts (private)

Game, market, selection, DK price + implied P, Pinnacle price + implied P, model P, EV%, Pin-vs-DK sanity check, time-to-tip, alert_id. Logged to `alerts` table for post-game reconciliation.

### 5.7 Public Web Dashboard

**Mobile-first, dark theme, responsive. Five pages:**

1. **Live Alerts (`/`)** — landing page; card feed of active +EV candidates; auto-updates via SSE; tap card → Prediction Inspector.
2. **CLV Tracker (`/clv`)** — rolling 30/90-day CLV chart (live vs backtest); breakdown by market and edge bucket.
3. **Backtest Explorer (`/backtest`)** — filter by season, market, edge threshold, execution scenario; results table + edge-size distribution chart.
4. **Prediction Inspector (`/alerts/{id}`)** — full alert details; SHAP feature contributions; "Why was this flagged?" narrative; similar historical situations.
5. **About / Methodology (`/about`)** — architecture diagram, data sources + limitations, CLV explanation, honest limitations section, tech stack, GitHub link, personal context.

### 5.8 Backend API (FastAPI)

Read-only public endpoints with rate limiting (60 req/min/IP):

- `GET /api/alerts/live`
- `GET /api/alerts/{alert_id}`
- `GET /api/clv?days=30`
- `GET /api/backtest?season=&market=&threshold=&scenario=`
- `GET /api/stream/alerts` (SSE)
- `GET /api/health`

CORS allowlist: Vercel frontend domain only.

### 5.9 Scheduler

GitHub Actions cron triggers, NBA-slate-aware. Odds polling, stats sync, injury sync, post-game reconciliation. Vercel cron pings `/api/health` every 10 min to prevent Render cold starts.

### 5.10 Live Performance Tracker

Post-game reconciliation. For every alert: compute outcome and CLV vs Pinnacle close. Running tally surfaced on the CLV Tracker page.

## 6. Data Models

See CLAUDE_START_HERE.md "Data Models" section. Every table has `as_of TIMESTAMPTZ NOT NULL`.

## 7. User Flow

### Developer (you)

- Receives private Telegram alerts during slate hours
- Reviews live performance via the public dashboard
- Iterates on features and thresholds based on CLV trends

### Public visitors (recruiters)

- Hit landing page → see live alerts (or empty state with explanation)
- Tap an alert → see model prediction explanation with SHAP features
- Visit CLV Tracker → see live vs backtest performance
- Visit Backtest Explorer → filter and explore historical performance
- Visit About → understand methodology and limitations

## 8. Success Metrics

- Pipeline reliability: ≥98% slate windows covered over 30 days
- Backtest: positive CLV in ≥2 of 4 execution scenarios on at least one market
- Live-vs-backtest gap: live CLV within ±1.5pp of backtest CLV (calibration check)
- Dashboard: deployed, mobile-responsive, loads under 2s on 4G
- Portfolio: README complete, all pages functional, deployment reproducible

## 9. Honest Limitations (must appear on About page and README)

1. Account-limit reality — real exploitation is constrained by book behavior toward winners
2. Injury data latency — Rotowire RSS is not a sharp-speed feed
3. Sample size — one NBA season ≈ 1230 games; props are larger but noisier
4. Why CLV beats ROI as the honest metric
5. Backtest leakage failure modes and how we guard against them
6. The public dashboard shows model outputs but does NOT recommend placing bets

## 10. Risks & Mitigations

- **Odds API free tier (500 req/month):** hourly polling stays within limit. If shortfall, reduce overnight cadence first.
- **Supabase pause (7-day inactivity):** daily scheduler keeps DB alive.
- **Render cold start:** Vercel keepalive cron prevents.
- **Public API abuse:** rate limiting + CORS restrict to known frontend.
- **NBA Stats API rate limiting:** respectful pacing, retries with exponential backoff, basketball-reference fallback for historical backfill.
- **Backtest overfitting:** walk-forward CV, regularization, baseline comparison.
- **SSE connection drops on free tier:** client-side reconnect with exponential backoff.

## 11. Build Order

See Progress Tracker in CLAUDE_START_HERE.md.

**Phase 1 (Pipeline) → Phase 2 (Frontend) → Phase 3 (Deployment).** Do not build frontend against mocks. Real data first.

## 12. Out of Scope for v1 (parking lot)

- Rebounds, assists, threes, combo props
- Multi-book support beyond DK + Pinnacle
- Live in-game betting markets
- Bankroll management / Kelly sizing
- User auth, comments, personalization
- WNBA, college, other sports
