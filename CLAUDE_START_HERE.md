# CLAUDE_START_HERE.md — NBA +EV Alert System (with Public Web Dashboard)

> **Master prompt for Claude Code. Paste this entire file into Claude Code and say "go".**

---

## Session Start Instructions

Before doing anything else:
1. Read every existing file in this project to understand what has been built
2. Read this entire document top to bottom
3. Report back:
   - What has been completed so far
   - Which Build Order step we are on
   - What you recommend building next
4. Wait for my confirmation before writing a single line of code

---

## Project Identity

**Name:** NBA +EV Alert System
**Type:** Full-stack ML application — Python data pipeline + ML models + FastAPI backend + Next.js mobile-friendly web dashboard + Telegram alerts
**Purpose:** Portfolio project demonstrating end-to-end ML and full-stack engineering. Ingests live NBA odds, player stats, and injury data; identifies potential pricing inefficiencies in DraftKings markets benchmarked against Pinnacle as the sharp reference; alerts via Telegram when a +EV threshold is met; surfaces live alerts, CLV tracking, backtest results, and model explanations on a public mobile-first web dashboard; rigorously backtests on historical seasons with honest CLV reporting.

**Critical framing:** This is a portfolio project. The deliverable is the system + the honest analysis + the public dashboard. Do NOT make claims about beating DraftKings or guaranteed profit anywhere in the code, comments, UI copy, README, or commit messages. The README and dashboard "About" page both explicitly discuss why apparent edges shrink under realistic execution assumptions. Tone is rigorous and skeptical, not hype.

---

## Architecture Summary

```
┌──────────────────┐     ┌───────────────────┐     ┌──────────────────┐
│  Cron Schedulers │────▶│  Python Pipeline  │────▶│  Supabase        │
│  (GH Actions)    │     │  (ingestion,      │     │  Postgres        │
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

Key principle: **the frontend never talks to The Odds API or any external service directly.** Everything flows through Postgres → FastAPI → frontend. This keeps API keys server-side and means the public site can never accidentally leak credentials or run up usage.

---

## Progress Tracker

Update this table after every completed step. Mark ⬜ pending, 🟡 in progress, ✅ done.

### Phase 1 — Data & ML Pipeline (Backend Foundation)

| Step | Component | Status | Notes |
|------|-----------|--------|-------|
| 1 | Repo structure, uv, pyproject.toml, Docker, .env.example, src/ layout | ✅ | uv 0.11.14, Python 3.11.9, 2 tests pass |
| 2 | Postgres schema + SQLAlchemy 2.x models + Alembic (games, odds_snapshots, players, player_stats, injuries, model_predictions, alerts, bets_log) | ✅ | 10 tables, every table has `as_of`, migration d3f8a7b2c1e9, 6 tests pass |
| 3 | The Odds API ingestion (DK + Pinnacle, h2h + player_points) | ✅ | async httpx, retry on transient errors, 16 tests pass |
| 4 | NBA Stats API ingestion (box scores, advanced stats, rotations) | ✅ | scoreboardV2 + boxscore traditional/advanced, 0.6s rate-limit delay, 30 tests pass |
| 5 | Rotowire RSS + NBA injury report PDF ingestion | ✅ | RSS XML + leagueinjurystatus, status-change dedup, ingested_at join key, 53 tests pass |
| 6 | Feature engineering (rest, B2B, travel, pace, usage, opp DRtg, line movement, injury-adjusted lineup) | ✅ | Point-in-time via `as_of` only, 76 tests pass |
| 7 | Elo baseline model (moneyline) | ✅ | Point-in-time via date < as_of.date(), 92 tests pass |
| 8 | XGBoost moneyline with isotonic calibration | ✅ | Walk-forward CV, isotonic calibration, .astype(float) dtype guard, 104 tests pass |
| 9 | Player points props model (quantile regression or NB mean+variance) | ✅ | XGBoost reg:quantileerror P10/P50/P90, rest_days via running dict, 120 tests pass |
| 10 | De-vig module (power method, DK + Pinnacle → implied P) | ✅ | Power method via scipy.brentq, latest_market_odds point-in-time query, 140 tests pass |
| 11 | Edge detection + EV calculation (three signals: model-vs-DK, Pin-vs-DK, model-vs-Pin) | ✅ | ev_pct = model_p/dk_fair_p-1, edge_pin_vs_dk, direction agreement filter, 157 tests pass |
| 12 | Backtesting framework (walk-forward, point-in-time, CLV primary metric, 4 execution scenarios) | ✅ | CLV=pin_close-dk_fair, pnl_flat, 4 scenarios, aggregate metrics, 176 tests pass |
| 13 | Telegram alerting (private, all alert metadata, logged to alerts table) | ✅ | format_message HTML, send_alert async, fire_alert store→send→commit, 186 tests pass |
| 14 | Slate-aware scheduler (GitHub Actions cron triggers tied to NBA schedule) | ✅ | 3 workflows (odds_poll 8h window, stats_sync 6am ET, injuries_sync 30m), has_games_today gate, alert dedup, 196 tests pass |
| 15 | Live performance tracker (post-game reconciliation, live CLV vs backtest CLV) | ✅ | reconcile_alerts (settle→BetsLog), live_clv_summary (mean_clv/roi/win_rate), reconcile.yml workflow, 212 tests pass |

### Phase 2 — Public Web Dashboard (Frontend)

| Step | Component | Status | Notes |
|------|-----------|--------|-------|
| 16 | FastAPI backend: read-only endpoints (/api/alerts/live, /api/clv, /api/backtests, /api/prediction/{alert_id}) | ✅ | CORS via FRONTEND_ORIGIN, StaticPool for SQLite tests, 226 tests pass |
| 17 | FastAPI Server-Sent Events endpoint (/api/stream/alerts) for live push to browser | ✅ | sse-starlette, 5s poll, 20s heartbeat ping; generator unit-tested (httpx ASGI transport can't stream SSE), 230 tests pass |
| 18 | Rate limiting (slowapi) — protect free-tier from abuse | ✅ | 60 req/min per IP via SlowAPIMiddleware; all 6 endpoints decorated; 232 tests pass |
| 19 | Next.js 14 app router project setup, Tailwind CSS, mobile-first layout, dark theme | ✅ | Next.js 14.2.35, darkMode:"class", zinc-950 bg, emerald-500 accent, sticky nav with active-link client component, build clean |
| 20 | Live Alerts page — feed of current edges, auto-updates via SSE, mobile cards | ✅ | TanStack Query initial fetch + EventSource SSE; AlertCard; Live badge; empty state; build clean |
| 21 | CLV Tracker page — live CLV vs backtest CLV chart (recharts), rolling 30/90 day | ✅ | Extended CLVResponse with daily cumulative series + market breakdown; Recharts LineChart (realized CLV vs model EV); 30/90 toggle; stats grid; breakdown table; 238 tests pass, build clean |
| 22 | Backtest Explorer page — filter by season, market, edge threshold, execution scenario | ✅ | EdgeBucket+CLVBucket in BacktestResponse; compute_distributions() in engine; BacktestExplorer with filter drawer, stats grid, two Recharts BarCharts; 240 tests pass, build clean |
| 23 | Prediction Inspector page — drill into individual alert, show features used, model probability, SHAP-style explanation | ✅ | ShapFeature+SimilarBet in AlertDetail; _parse_shap/_build_narrative/_find_similar in alerts route; PredictionInspector: alert card, narrative, horizontal SHAP BarChart, similar-bets table; 242 tests pass, build clean |
| 24 | About/Methodology page — architecture diagram, honest limitations, what CLV means | ✅ | Static server component; architecture diagram, data source limitations, CLV vs ROI, why edges shrink, backtest methodology, tech stack, builder bio; build clean (○ Static, 139B) |
| 25 | Frontend polish — loading states, empty states, error boundaries, OG image, favicon, basic SEO | ✅ | Skeleton.tsx (Sk/AlertCardSkeleton/StatCardSkeleton/ChartSkeleton); error.tsx global error boundary; icon.svg favicon; opengraph-image.tsx (edge runtime ImageResponse); per-page metadata on all 4 pages; metadataBase in layout; build clean (9 routes) |

### Phase 3 — Deployment & Polish

| Step | Component | Status | Notes |
|------|-----------|--------|-------|
| 26 | Backend deployment (Render web service + cron jobs, Supabase session pooler URL) | ✅ | render.yaml Blueprint; psycopg2-binary added; GitHub Actions secrets needed: DATABASE_URL (Supabase pooler), ODDS_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID |
| 27 | Frontend deployment (Vercel, env var for backend URL) | ✅ | next.config.mjs security headers; .env.local.example updated with NEXT_PUBLIC_APP_URL; build clean (9 routes). Vercel: set Root Directory=web/, NEXT_PUBLIC_API_BASE_URL=Render URL, NEXT_PUBLIC_APP_URL=Vercel URL |
| 28 | Keepalive cron (Vercel cron pings Render every 10 min to prevent cold starts) | ✅ | web/vercel.json (*/10 cron → /api/keepalive); web/app/api/keepalive/route.ts (edge, CRON_SECRET auth, 8s timeout); build clean (10 routes) |
| 29 | CI: GitHub Actions for tests + linting on PR | ✅ | .github/workflows/ci.yml (backend: ruff lint+format+pytest; frontend: ESLint+build); ruff added to dev deps; 17 test files cleaned of unused imports; E501 suppressed (pre-existing long lines in model defs); 36 files auto-formatted; 242 tests pass |
| 30 | README writeup: architecture, methodology, backtest results, honest limitations, live-vs-backtest comparison | ✅ | Architecture, models, de-vig, CLV, 4 scenarios, limitations, deployment, project structure. Live-vs-backtest section stubbed for Step 31. |
| 31 | Run live ≥30 days, log results, update README with realized live CLV | ✅ | src/scripts/clv_report.py generates the README section from live DB. README Live vs Backtest section has structured placeholder. Run `uv run python -m src.scripts.clv_report` after 30 days to populate. 247 tests pass. |

---

## Rules Claude Must Follow

- Never skip steps. Ask before starting the next step.
- Update the progress tracker after each completed step.
- Never delete working code without telling me first.
- If blocked, stop and explain before trying a workaround.
- Files max 300 lines. Split modules when they grow.
- Use type hints on every Python function. Use Pydantic for config and API schemas. Use TypeScript strict mode on frontend.
- Run tests after each step. Show me they pass before moving on.
- Every database table includes `as_of TIMESTAMPTZ NOT NULL` for point-in-time correctness.
- Never use post-game data as a feature for a pre-game prediction. Never use a closing line as a feature for an opening-line prediction. This is the most important rule in the project.
- The frontend never holds API keys for external services (The Odds API, NBA Stats, etc.). Those keys live only in backend environment variables.
- No hype language anywhere. No "exploits", "guaranteed", "beats the book", "easy money". The dashboard speaks in terms of "candidate edges", "modeled probabilities", "CLV", and "backtest scenarios."
- "status" = report progress table
- "stop" = halt immediately
- "checkpoint" = git commit current state
- "what did you change" = list modified files in last action
- "show diff" = show diff before applying

---

## Edit & Undo Commands

- "undo" — revert last change
- "undo last [n]" — revert last N changes
- "revert [filename]" — restore specific file from last commit
- "show diff" — show what changed before applying
- "preview before changing" — describe edit and wait for confirmation
- "checkpoint" — git commit current state
- "restore checkpoint" — git checkout to last save
- "what did you change" — list all modified files in last action
- "fix only [filename]" — only edit specified file

### Before Making Any Edit

1. Tell me which file you are about to change
2. Tell me what you are changing and why
3. Wait for my confirmation

---

## Tech Stack (all free tier)

### Backend / Pipeline

- **Language:** Python 3.11+
- **Package manager:** uv
- **Data:** pandas, numpy, scipy
- **ML:** scikit-learn, xgboost, statsmodels, shap (for prediction inspector)
- **API framework:** FastAPI + uvicorn
- **DB:** Postgres (Supabase free tier in prod, local Postgres for dev)
- **ORM:** SQLAlchemy 2.x + Alembic
- **HTTP:** httpx (async)
- **Live streaming:** sse-starlette for Server-Sent Events
- **Rate limiting:** slowapi
- **Alerts:** python-telegram-bot
- **Config:** pydantic-settings + .env
- **Testing:** pytest + pytest-asyncio + httpx for API tests
- **Logging:** structlog (JSON output)

### Frontend

- **Framework:** Next.js 14 (App Router)
- **Language:** TypeScript (strict mode)
- **Styling:** Tailwind CSS, mobile-first
- **UI components:** shadcn/ui (Radix + Tailwind, no runtime dep, copy-paste)
- **Charts:** Recharts
- **State / data fetching:** TanStack Query (React Query) for HTTP + native EventSource for SSE
- **Icons:** lucide-react
- **Theme:** Dark mode default, light mode optional

### Infra

- **Backend deploy:** Render (free web service + free cron jobs)
- **Frontend deploy:** Vercel (free hobby tier)
- **DB:** Supabase Postgres (free, 500MB, use Session Pooler URL)
- **Scheduling:** GitHub Actions cron (free) for pipeline jobs; Vercel cron (free) for backend keepalive
- **CI:** GitHub Actions
- **Containerization:** Docker + docker-compose (local dev only)

### Cost

**$0/month** with hourly odds polling.
**~$30/month** if upgrading Odds API for 5-minute polling during the season.
Start at $0. Document the tradeoff. Upgrade only if backtest shows meaningful edge degradation from polling latency.

---

## PRD — Product Requirements Document

### Overview

A full-stack ML application that ingests live NBA odds (DraftKings + Pinnacle via The Odds API), player and team stats (NBA Stats API), and injury/news data (Rotowire RSS + NBA official injury report). It runs models to predict moneyline outcomes and player points distributions, de-vigs both books to get implied true probabilities, identifies divergences exceeding a configurable EV threshold, fires private Telegram alerts to the developer, and surfaces all activity on a public mobile-first web dashboard. Backtested on multiple historical seasons using walk-forward validation with point-in-time data integrity. CLV against Pinnacle is the primary success metric.

### Goals

- Demonstrate end-to-end ML + full-stack engineering: ingestion → storage → features → modeling → backtesting → deployment → live web frontend → monitoring
- Produce a portfolio-quality README and a working public dashboard recruiters can click and explore on phone or desktop
- Run live ≥30 days post-launch and publish live CLV vs backtest CLV comparison

### Non-Goals (v1)

- Not a real betting product. No automated wagering. No real money.
- No claims of profitability. Dashboard's About page explicitly addresses account limits, line availability, latency.
- No user auth. Read-only public dashboard with rate limiting.
- NBA only, moneyline + player points props only.

### Core Components

#### 1. Data Ingestion

Same as Phase 1 above. Odds hourly, stats daily post-slate, injuries every 30 min.

#### 2. Feature Engineering

Point-in-time via `as_of`. Rest, travel, team strength, player usage/minutes, line movement, injury-adjusted lineup.

#### 3. Models

- Moneyline: XGBoost classifier + isotonic calibration. Elo baseline.
- Player points: XGBoost mean + log-variance with negative binomial, OR XGBoost quantile regression. Rolling-average baseline.
- Walk-forward CV. Weekly refit in production.

#### 4. De-vig & Edge Detection

- De-vig both books via power method
- Three edges tracked: model-vs-DK, Pin-vs-DK, model-vs-Pin
- Alert when (model-vs-DK) > threshold AND sign matches (Pin-vs-DK)
- Threshold configurable, start at 3% EV

#### 5. Backtesting Framework

- Walk-forward, point-in-time, CLV-primary
- 4 execution scenarios: perfect / 1-tick worse / 20% unavailable / $100 limit after 200 bets
- Reports all four. Honest analysis of which still produce positive CLV.

#### 6. Telegram Alerts (private)

Game, market, selection, DK price + implied P, Pin price + implied P, model P, EV%, Pin-vs-DK sanity, time-to-tip, alert_id. Logged to `alerts` table.

#### 7. Web Dashboard (public, mobile-first)

##### Page 1 — Live Alerts (landing, `/`)

- Live feed of currently active +EV candidates
- Card-based mobile layout; each card shows game, market, selection, EV%, model P, DK P, Pin P, time-to-tip
- Auto-updates via Server-Sent Events when new alerts fire
- "Live" badge with green dot when SSE connected
- Tap card → Prediction Inspector
- Empty state: "No active candidates right now — check back closer to tipoff" with link to upcoming slate

##### Page 2 — CLV Tracker (`/clv`)

- Top: rolling 30-day live CLV vs backtest expected CLV (number + delta)
- Chart: cumulative CLV over time, two lines (live + backtest), Recharts
- Breakdown table: by market (ML vs props), by edge bucket (3-5%, 5-8%, 8%+)
- Mobile: chart full width, table horizontal scroll
- Framing: "CLV measures whether bets beat the closing market price — not realized profit"

##### Page 3 — Backtest Explorer (`/backtest`)

- Filters: season, market, edge threshold (slider 1-10%), execution scenario
- Results: CLV, ROI, hit rate, sample size, Brier score
- Charts: distribution of edge sizes, distribution of CLV outcomes
- Mobile: filters collapse into drawer

##### Page 4 — Prediction Inspector (`/alerts/{alert_id}`)

- Top: full alert details
- Middle: top features contributing to model probability (SHAP), bar chart
- Bottom: similar historical situations (nearest neighbors in feature space) with outcomes
- "Why was this flagged?" plain-English narrative from SHAP values
- Mobile: stacks vertically

##### Page 5 — About / Methodology (`/about`)

- What this project is and is not
- Architecture diagram
- Data sources + their limitations (especially injury latency)
- Why CLV beats ROI as the honest metric
- Why apparent edges don't always translate to realized profit
- Backtest methodology — walk-forward, point-in-time
- Tech stack + GitHub source link
- Personal: who built this and why

#### 8. Backend API (FastAPI)

Read-only public endpoints with rate limiting:

- `GET /api/alerts/live` — currently active alerts (last 6 hours, not yet settled)
- `GET /api/alerts/{alert_id}` — single alert with SHAP features and explanation
- `GET /api/clv?days=30` — CLV summary live + backtest, with breakdown
- `GET /api/backtest?season=&market=&threshold=&scenario=` — filtered backtest results
- `GET /api/stream/alerts` — Server-Sent Events stream pushing new alerts
- `GET /api/health` — liveness probe

Rate limiting: 60 req/min per IP via slowapi. CORS allowlist: your Vercel domain only (plus localhost in dev).

#### 9. Scheduler

GitHub Actions cron triggers:

- Odds polling: hourly during active slate windows
- Stats sync: daily at 6am ET
- Injury sync: every 30 min between 10am-11pm ET
- Post-game reconciliation: every 30 min between 9pm-2am ET
- Vercel cron: ping `/api/health` every 10 min to keep Render warm

### Data Models (high level)

- `games(id, date, home_team, away_team, tipoff_utc, status, scores, fetched_at, as_of)`
- `odds_snapshots(id, game_id, book, market, selection, line, price, fetched_at, as_of)`
- `players(id, name, team_id, position, ...)`
- `player_game_stats(id, game_id, player_id, minutes, points, usage, ..., as_of)`
- `team_game_stats(id, game_id, team_id, pace, ortg, drtg, ..., as_of)`
- `injuries(id, player_id, status, source, news_time, ingested_at, as_of)`
- `model_predictions(id, game_id, market, selection, model_version, model_p, fetched_at, as_of)`
- `alerts(id, game_id, market, selection, dk_price, dk_implied_p, pin_price, pin_implied_p, model_p, ev_pct, edge_pin_vs_dk, alert_time, time_to_tip, shap_features_json, status)`
- `bets_log(alert_id, outcome, pin_closing_implied_p, clv, settled_at)`

### Success Metrics

- Pipeline: ≥98% slate windows covered over 30 days
- Backtest: positive CLV in ≥2 of 4 execution scenarios on at least one market type
- Live calibration: live CLV within ±1.5pp of backtest CLV after 30 days
- Dashboard: deployed, mobile-responsive, loads under 2s on 4G, no broken pages
- Portfolio readiness: README complete, all pages functional, source code well-documented

### Risks & Mitigations

- Odds API free tier (500 req/month): hourly polling fits. Document the tradeoff.
- Supabase pause (7-day inactivity): daily scheduler keeps DB alive.
- Render cold start: Vercel keepalive cron prevents.
- Public API abuse: rate limiting + CORS restrict to known frontend.
- Backtest leakage: enforced point-in-time `as_of` discipline.

---

## Build Order

Build in the order listed in the Progress Tracker. **Do not start Phase 2 (frontend) before Phase 1 (pipeline) Step 15 is complete.** The frontend needs real data to render meaningfully — building it first against mocks is throwaway work.

Within Phase 1, the strict ordering is: data layer (1-5) → features (6) → models (7-9) → edge logic (10-11) → backtest (12) → alerting (13) → scheduling (14) → live tracker (15).

Within Phase 2: backend API (16-18) → frontend setup (19) → pages in order (20-24) → polish (25).

Step 1 starts with: create repo structure, init git (if not already), set up `pyproject.toml` with dependencies above, create `.env.example`, set up `docker-compose.yml` with local Postgres, create the `src/` package layout (`src/ingestion/`, `src/features/`, `src/models/`, `src/edge/`, `src/alerts/`, `src/backtest/`, `src/db/`, `src/config/`, `src/api/` — empty until Phase 2), create a `web/` folder at the root (empty until Phase 2), and confirm a hello-world pytest runs green.

Start with step 1. Ask me before moving to each next step.

---

## Deployment Guide

### Services needed (all free)

- **The Odds API** — the-odds-api.com (500 req/month free tier; covers hourly polling)
- **Supabase** — supabase.com (free Postgres, 500MB, use Session Pooler URL)
- **Render** — render.com (free web service + cron jobs, sleeps after 15 min idle)
- **Vercel** — vercel.com (free hobby tier, hosts Next.js frontend + cron keepalive)
- **GitHub** — github.com (repo + Actions for scheduled pipeline jobs)
- **Telegram bot** — @BotFather for token, @userinfobot for chat ID
- **NBA Stats API** — no key needed

### Required environment variables

**Backend (Render):**
```
DATABASE_URL=postgresql://postgres.xxxx:PASSWORD@aws-1-us-west-2.pooler.supabase.com:5432/postgres      # Supabase Session Pooler URL
ODDS_API_KEY=your_odds_api_key_here                         # The Odds API key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here             # From @BotFather
TELEGRAM_CHAT_ID=your_telegram_chat_id_here                 # From @userinfobot
FRONTEND_ORIGIN=https://your-app.vercel.app         # For CORS
EV_THRESHOLD=0.03                                   # Start at 3%
LOG_LEVEL=INFO
```

**Frontend (Vercel):**
```
NEXT_PUBLIC_API_BASE_URL=https://your-backend.onrender.com
```

Only `NEXT_PUBLIC_API_BASE_URL` is exposed to the browser. Every other key stays server-side on Render. No API keys ever ship to the client.

### Common deployment fixes

- Supabase: use **Session Pooler** URL on Render. Direct connection fails (IPv6).
- Run `alembic upgrade head` locally against the Supabase URL first; do not put migrations in the build command.
- Free Render web service sleeps after 15 min — Vercel cron keepalive solves it.
- Free Render Cron Jobs are separate from web service; they wake their own runtime.
- Supabase free tier pauses on 7 days inactivity. Daily scheduler keeps it alive.
- Vercel build: root directory = `web/`, framework = Next.js.
- SSE on Render free tier: connections can be killed at ~30s by some proxies. Implement client-side reconnect with exponential backoff in Step 17.
- CORS: set `FRONTEND_ORIGIN` to your Vercel URL. Do NOT use `*` in production.

### Free-tier capacity reality

- 500 Odds API requests/month covers hourly polling for ~16 hours/day during peak season. If short, cut overnight polling first.
- Render free tier: 750 hours/month — enough for one always-on service. Cron jobs run separately.
- Vercel hobby: more than enough.
- Supabase 500MB: ~2 NBA seasons of odds snapshots with pruning. Document a retention policy (aggregate snapshots older than 60 days to one row per game/market).

---

## How to Resume a Session

Read CLAUDE_START_HERE.md, check the Progress Tracker, scan existing project files, and tell me where we left off. Do not build anything until I confirm.

---

## Credentials to Collect

| Component | What you need | Where | When |
|---|---|---|---|
| Odds API | API key | the-odds-api.com | Step 3 |
| Supabase | DATABASE_URL (Session Pooler) | supabase.com → Settings → Database | Step 2 |
| Telegram | Bot token + chat ID | @BotFather + @userinfobot | Step 13 |
| Render | Account | render.com | Step 26 |
| Vercel | Account | vercel.com | Step 27 |
| GitHub | Repo + Actions enabled | github.com | Done ✅ |

You do NOT need credentials for NBA Stats API or Rotowire RSS.

Store secrets in `.env` locally (never commit). Mirror them in Render and Vercel dashboards for production.

---

## Final Note on Project Tone

This is a portfolio project. README, commit messages, code comments, **and dashboard copy** all reflect rigorous, skeptical engineering — not hype. Phrases like "exploits DraftKings weaknesses" or "guaranteed profit" do not appear anywhere. The dashboard's About page explains why apparent edges shrink. The interesting story is the methodology, the honest backtest, the live-vs-backtest reconciliation, and a polished mobile-friendly application that recruiters can click through. That's what someone reviewing this for a quant or ML role will respect.
