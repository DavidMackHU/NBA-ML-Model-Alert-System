# NBA +EV Alert System

[![CI](https://github.com/DavidMackHU/NBA-ML-Model-Alert-System/actions/workflows/ci.yml/badge.svg)](https://github.com/DavidMackHU/NBA-ML-Model-Alert-System/actions/workflows/ci.yml)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![Next.js 14](https://img.shields.io/badge/next.js-14-black)

A full-stack ML application that ingests live NBA odds, player stats, and injury data; runs calibrated models to identify candidate pricing inefficiencies between DraftKings and Pinnacle; fires private Telegram alerts when a configurable EV threshold is met; and surfaces live alerts, CLV tracking, and backtest results on a public mobile-first web dashboard.

**This is a portfolio project.** The deliverable is the system, the honest analysis, and the methodology documentation — not a claim of profitability. Apparent pre-game edges routinely shrink under realistic execution conditions. See [Why edges shrink](#why-edges-shrink) for the full discussion.

**Live dashboard:** _link added after deployment_  
**Source:** [github.com/DavidMackHU/NBA-ML-Model-Alert-System](https://github.com/DavidMackHU/NBA-ML-Model-Alert-System)

---

## Table of Contents

- [Architecture](#architecture)
- [Pipeline Walkthrough](#pipeline-walkthrough)
- [Models](#models)
- [De-vig and Edge Detection](#de-vig-and-edge-detection)
- [Backtesting Framework](#backtesting-framework)
- [Backtest Results](#backtest-results)
- [Live vs Backtest Comparison](#live-vs-backtest-comparison)
- [Why CLV, Not ROI](#why-clv-not-roi)
- [Why Edges Shrink](#why-edges-shrink)
- [Tech Stack](#tech-stack)
- [Local Development](#local-development)
- [Deployment](#deployment)
- [Project Structure](#project-structure)

---

## Architecture

```
┌──────────────────┐     ┌───────────────────┐     ┌──────────────────┐
│  Cron Schedulers │────▶│  Python Pipeline  │────▶│  Supabase        │
│  (GitHub Actions)│     │  (ingestion,      │     │  Postgres        │
└──────────────────┘     │   features, ML)   │◀────│  (single source  │
                         └────────┬──────────┘     │   of truth)      │
                                  │                └─────────┬────────┘
                                  ▼                          │
                         ┌──────────────────┐                │
                         │  Telegram Bot    │                │
                         │  (private alert) │                │
                         └──────────────────┘                │
                                                             │
                         ┌──────────────────┐                │
                         │  FastAPI Backend │◀───────────────┘
                         │  (read API + SSE │
                         │   live stream)   │
                         └────────┬─────────┘
                                  │ HTTPS + SSE
                                  ▼
                         ┌──────────────────┐
                         │  Next.js Web App │
                         │  (mobile-first   │
                         │   public dash)   │
                         └──────────────────┘
```

**Key design principle:** the frontend never calls The Odds API or any external data service. All API keys live in backend environment variables on Render. The browser receives data exclusively through the FastAPI layer, which means the public dashboard cannot accidentally leak credentials or run up API usage.

---

## Pipeline Walkthrough

### 1. Data Ingestion

Three independent ingestion jobs run on GitHub Actions cron schedules:

| Job | Schedule | Source |
|-----|----------|--------|
| Odds polling | Hourly during 8-hour pre-game windows | The Odds API (DraftKings + Pinnacle, h2h + player_points markets) |
| Stats sync | Daily at 6 am ET after overnight games settle | NBA Stats API (box scores, advanced stats, rotations) |
| Injury sync | Every 30 minutes, 10 am – 11 pm ET | Rotowire RSS + NBA official injury report PDF |

Odds snapshots include American odds and the fetch timestamp. Every row in every table carries `as_of TIMESTAMPTZ NOT NULL` — the wall-clock time of the API call — so all downstream queries can be bounded to the exact moment of prediction.

### 2. Feature Engineering

Features are computed point-in-time using the `as_of` timestamp as a strict upper bound. No same-day game data is ever included in a pre-game feature set.

| Feature group | Description |
|---------------|-------------|
| Rest and schedule | Days since last game, back-to-back indicator, games in last 7 days |
| Travel | Timezone delta and estimated flight distance between game cities |
| Team strength | Rolling pace (possessions/48), offensive and defensive rating (trailing 10 games) |
| Player props | Rolling minutes, usage rate, position-adjusted shot distribution, home/away splits |
| Lineup adjustment | Injury-adjusted effective lineup rating based on current injury report |
| Line movement | Opening-to-current price delta on DraftKings (point-in-time: no closing line used as a feature) |

### 3. Modeling

See [Models](#models) below.

### 4. De-vig and Edge Detection

See [De-vig and Edge Detection](#de-vig-and-edge-detection) below.

### 5. Backtesting

Walk-forward historical evaluation with four execution scenarios. See [Backtesting Framework](#backtesting-framework).

### 6. Alerting

When a candidate edge clears the EV threshold, the pipeline stores the alert to Postgres and fires a Telegram message containing: game, market, selection, DK price + implied probability, Pinnacle price + implied probability, model probability, EV%, Pinnacle-vs-DK edge, time to tipoff, and an `alert_id` for later reconciliation.

### 7. Live Performance Tracking

A post-game reconciliation job runs nightly. It matches settled alerts to their outcomes and computes closing line value (CLV) for each bet using Pinnacle's closing price. Rolling CLV, ROI, win rate, and mean EV are tracked in `bets_log` and surfaced on the CLV Tracker page.

---

## Models

### Elo Baseline (moneyline)

A standard Elo rating system seeded at 1,500 for all teams, updated after each game using K=20. Home-court advantage is modeled as a 100-point Elo offset (equivalent to ~3–4 percentage points in win probability). Ratings are computed point-in-time: only games with `date < prediction_date` and `status = 'final'` are used.

This model serves as the interpretable lower bound. If the XGBoost moneyline model consistently agrees with Elo on direction, that agreement is one of three signals required for an alert to fire.

### XGBoost Moneyline (primary)

XGBoost classifier trained on the feature set above. Walk-forward cross-validation: train on seasons 1..N-1, predict season N, then roll forward. Raw probabilities are calibrated with isotonic regression to correct for XGBoost's tendency to compress probabilities toward 0.5.

Output: `model_p` — the calibrated probability that the flagged team wins.

### XGBoost Player Props (quantile regression)

XGBoost quantile regressor producing P10/P50/P90 estimates for player points. The P50 (median) is used as the model's point estimate. Props features mirror the moneyline set but emphasize player-level statistics: rolling scoring average, usage rate, minutes consistency, and opponent defensive rating allowed to the player's position.

The props model is intentionally conservative — it uses the median of a wide distribution rather than a point forecast, and the EV calculation applies the same de-vig and edge-agreement filters as the moneyline.

---

## De-vig and Edge Detection

### De-vig: Power Method

Both DraftKings and Pinnacle odds are de-vigged using the power method (via `scipy.brentq` root-finding). The power method finds the exponent `k` such that:

```
(1/p_home)^k + (1/p_away)^k = 1
```

This yields `dk_fair_p` and `pin_fair_p` — the books' implied true probabilities stripped of vig — as well as `pin_closing_fair_p` computed from Pinnacle's closing line at reconciliation time.

### Three Edge Signals

For each market and selection, the system computes:

| Signal | Formula | Interpretation |
|--------|---------|----------------|
| Model vs DK | `model_p / dk_fair_p - 1` | How much the model's probability exceeds DK's fair price |
| Pin vs DK | `pin_fair_p / dk_fair_p - 1` | How much the sharp market differs from DK's price |
| Model vs Pin | `model_p / pin_fair_p - 1` | Whether the model agrees with Pinnacle's direction |

**Alert condition:** `model_p / dk_fair_p - 1 > EV_THRESHOLD` AND `sign(model_p - dk_fair_p) == sign(pin_fair_p - dk_fair_p)`. The sign-agreement filter requires that Pinnacle is pricing the same side as the model before an alert fires. This reduces alerts on situations where the model disagrees with the sharpest book in the world.

---

## Backtesting Framework

### Walk-Forward Validation

Models are trained exclusively on seasons prior to the test period. Feature computation during the backtest is bounded by the in-sample prediction date — the same `as_of` discipline as production. No information from game outcomes, closing lines, or post-game stats leaks into pre-game predictions.

### Four Execution Scenarios

| Scenario | Description | Interpretation |
|----------|-------------|----------------|
| Perfect | Full edge captured at alert price | Upper bound; never achievable in practice |
| Tick Worse | +0.5 pp added to `dk_fair_p` | Models ~5 cents of vig friction from line movement |
| 20% Unavailable | Random 20% of bets excluded from results | Models limits, early line pulls, and book restrictions |
| Limit After 200 | Bets 201+ capped at $100 | Models account restriction that kicks in after a profitable track record |

All four scenarios are computed and reported together. No scenario is presented as "the answer" — the honest picture requires seeing all four.

### Primary Metric: CLV

```
CLV per bet = pin_closing_fair_p - dk_fair_p
```

Positive CLV means the bet was placed at better odds than where the Pinnacle closing line settled. Because sharp money drives Pinnacle's line toward true probability, consistent positive CLV is evidence that the model identified pricing inefficiencies before the market corrected them.

ROI is reported alongside CLV. Over sample sizes typical of a single NBA season (300–1,200 settled bets), ROI carries very high variance and is not a reliable model quality indicator. Mean CLV per bet over a rolling window is the headline health metric.

---

## Backtest Results

Full historical backtest results — filterable by season, market, edge threshold, and execution scenario — are available in the live **Backtest Explorer** page of the dashboard. Results are updated each season as new data becomes available.

Summary interpretation guidelines:
- Positive mean CLV in the realistic scenario (Tick Worse) on the moneyline market is the primary success condition.
- Player props results carry wider confidence intervals due to shallower Pinnacle closing-line liquidity.
- Brier score is reported alongside CLV to measure calibration quality independently of edge.
- All results should be treated as directional signals over the sample sizes a single NBA season provides — not precise probability estimates.

---

## Live vs Backtest Comparison

<!-- CLV report generated YYYY-MM-DD — last 30 days -->

_Last updated: pending ≥30 days of live operation_

### Rolling CLV Summary

| Window | Bets | Settled | Mean CLV | Mean EV (model) | ROI | Win Rate |
|--------|------|---------|----------|-----------------|-----|----------|
| 30 days | — | — | — | — | — | — |
| 90 days | — | — | — | — | — | — |

> **Mean CLV** = mean(pin_closing_fair_p − dk_fair_p) per settled bet, expressed in probability points. Positive = beat Pinnacle closing line on average.

### By Market

| Market | Bets | Settled | Mean CLV | Mean EV |
|--------|------|---------|----------|---------|
| h2h | — | — | — | — |
| player_points | — | — | — | — |

_The CLV Tracker page on the live dashboard shows the full daily cumulative series and auto-updates after each reconciliation run._

**Regenerating this section:** after ≥30 days of live operation, run:

```bash
uv run python -m src.scripts.clv_report
```

Paste the output in place of this section. The script queries `bets_log` directly and formats the tables above.

---

## Why CLV, Not ROI

ROI measures win/loss outcomes. A model with genuine edge can post negative ROI over a season through variance alone — you need 500+ bets before ROI estimates stabilize. One bad stretch of outcomes does not imply a broken model.

CLV measures whether the bet was placed at better odds than where the market ultimately settled. Sharp money continuously drives Pinnacle's closing line toward the true probability, so consistent positive CLV is the best available evidence of skill at identifying mispricing before the market corrects it.

CLV is not without limitations:
- It can be positive while ROI is running negative over a bad-luck window.
- For player props, Pinnacle's closing line has shallower liquidity than for moneylines — the signal is noisier.
- CLV measured in probability points (fair probability delta) is the most direct version. The dashboard reports this alongside a dollars-and-cents ROI view for context.

---

## Why Edges Shrink

This section exists because "positive backtest CLV" is not the same as "profitable in practice." The gap between the two is wide, and it is worth being explicit about why.

**Line movement between alert and execution.** By the time an alert fires and a bet is placed, DraftKings may have already moved the line toward fair value. The edge computed at alert time may not exist at execution time. The realistic scenario in the backtest models this with a 0.5 pp de-vig penalty, but actual movement can exceed this.

**DraftKings vig.** DK charges roughly 5–8% juice on moneylines and more on props. The model edge must exceed the vig to produce positive expected value. At 3% EV threshold, many alerts are marginal after realistic vig is applied.

**Market efficiency and sharp competition.** Professional bettors watch the same signals. When the model identifies an apparent edge, faster actors with more data may have already moved the market. Lines in liquid markets close quickly.

**Model calibration drift.** Calibration drifts as rosters, coaching, pace, and injuries evolve within a season. Walk-forward retraining partially addresses this but does not eliminate it. The props model is particularly vulnerable to mid-season roster changes.

**Sample size.** A single NBA season yields roughly 1,200 games and a few thousand player prop markets. Reliable model evaluation — to the precision that distinguishes a 2% positive CLV from noise — requires multiple seasons of walk-forward data. Backtest results from one or two seasons are directional signals, not precise estimates.

**Account restrictions.** Books limit or close accounts that win consistently. This project does not automate wagering, but any interpretation of backtest results should account for the practical ceiling on bet size and account longevity.

---

## Tech Stack

| Layer | Tools |
|-------|-------|
| Language | Python 3.11, TypeScript (strict) |
| Package management | uv (Python), npm (Node) |
| ML / data | pandas, numpy, scikit-learn, XGBoost, SHAP, scipy |
| Database | Postgres (Supabase) + SQLAlchemy 2.x + Alembic |
| Backend API | FastAPI + uvicorn, sse-starlette, slowapi |
| Frontend | Next.js 14 App Router, Tailwind CSS, Recharts |
| Data fetching | TanStack Query v5, native EventSource (SSE) |
| Alerts | python-telegram-bot |
| Config | pydantic-settings + .env |
| Testing | pytest, pytest-asyncio, httpx |
| Linting | ruff |
| Scheduling | GitHub Actions cron |
| Backend deploy | Render (free web service) |
| Frontend deploy | Vercel (free hobby tier) |
| Database host | Supabase (free, 500 MB) |
| Containerization | Docker + docker-compose (local dev only) |

**Total infrastructure cost: $0/month** on the free tiers listed above, with hourly odds polling. Upgrading to 5-minute polling during the season requires a paid Odds API plan (~$30/month).

---

## Local Development

**Prerequisites:** Python 3.11+, `uv`, Node.js 20+, Docker (for local Postgres).

```bash
# Clone
git clone https://github.com/DavidMackHU/NBA-ML-Model-Alert-System.git
cd NBA-ML-Model-Alert-System

# Python environment
uv sync

# Copy env file and fill in values
cp .env.example .env

# Start local Postgres
docker compose up -d

# Run migrations
uv run alembic upgrade head

# Run tests
uv run pytest --tb=short -q

# Start FastAPI backend
uv run uvicorn src.api.app:app --reload

# Frontend (separate terminal)
cd web
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm install
npm run dev
```

The pipeline scripts can be run individually for local testing:

```bash
uv run python -m src.scripts.ingest_odds
uv run python -m src.scripts.ingest_nba_stats
uv run python -m src.scripts.ingest_injuries
```

---

## Deployment

### Backend (Render)

A `render.yaml` Blueprint is included. Connect the GitHub repo to Render, select "Use existing render.yaml", and fill in the required environment variables in the Render dashboard (all marked `sync: false` in the Blueprint):

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Supabase Session Pooler URL (not the direct connection URL — direct fails on IPv6) |
| `ODDS_API_KEY` | From [the-odds-api.com](https://the-odds-api.com) |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | From @userinfobot |
| `FRONTEND_ORIGIN` | Your Vercel URL (for CORS) |

Run `alembic upgrade head` once locally against the Supabase URL to initialize the schema before the first deploy.

### Frontend (Vercel)

Import the repo in Vercel. Set:
- **Root Directory:** `web/`
- **Framework:** Next.js (auto-detected)
- **Environment variables:** `NEXT_PUBLIC_API_BASE_URL` (your Render URL), `NEXT_PUBLIC_APP_URL` (your Vercel URL)

The keepalive cron (`web/vercel.json`) pings `/api/health` on Render every 10 minutes to prevent cold starts on the free tier.

### GitHub Actions Secrets

Add these secrets to the repository for the pipeline cron jobs:

| Secret | Purpose |
|--------|---------|
| `DATABASE_URL` | Supabase Session Pooler URL |
| `ODDS_API_KEY` | The Odds API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |

The CI workflow (`.github/workflows/ci.yml`) runs on every push and PR with no database connection — all 242 tests use in-memory SQLite.

---

## Project Structure

```
src/
├── api/            # FastAPI app, routes, schemas, rate limiting, SSE
├── backtest/       # Walk-forward engine, 4 execution scenarios, CLV computation
├── db/             # SQLAlchemy models, Alembic migrations, base
├── edge/           # De-vig (power method), EV calculation, edge detection
├── features/       # Point-in-time feature engineering
├── ingestion/      # Odds API, NBA Stats API, injury report ingestors
├── models/         # Elo baseline, XGBoost moneyline, XGBoost props
├── scripts/        # CLI entry points for each pipeline stage
└── tracker/        # Post-game reconciliation, live CLV computation

web/
├── app/            # Next.js App Router pages and API routes
│   ├── page.tsx          # Live Alerts feed (SSE)
│   ├── clv/              # CLV Tracker (Recharts, 30/90-day toggle)
│   ├── backtest/         # Backtest Explorer (filter drawer, distributions)
│   ├── alerts/[id]/      # Prediction Inspector (SHAP, similar bets)
│   ├── about/            # Methodology and honest limitations
│   └── api/keepalive/    # Edge function keepalive for Render
└── components/     # AlertCard, PredictionInspector, CLVTracker, BacktestExplorer

.github/workflows/
├── ci.yml              # Ruff + pytest + ESLint + Next.js build on PR
├── odds_poll.yml       # Hourly odds ingestion during slate windows
├── stats_sync.yml      # Daily box score sync
├── injuries_sync.yml   # 30-minute injury report sync
└── reconcile.yml       # Nightly post-game CLV reconciliation

tests/              # 242 tests; all use in-memory SQLite (no external DB needed)
alembic/            # Database migrations
render.yaml         # Render Blueprint for backend deployment
```

---

## License

MIT. This project is provided as-is for educational and portfolio purposes. It does not constitute financial or gambling advice.
