import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "About & Methodology | NBA +EV Alert System",
  description:
    "How the NBA +EV Alert System works, what CLV measures, why edges shrink, and honest backtest methodology.",
};

const GITHUB_URL = "https://github.com/DavidMackHU";

const ARCH_DIAGRAM = `
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
`.trim();

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900">
      <div className="border-b border-zinc-800 px-5 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
          {title}
        </h2>
      </div>
      <div className="space-y-3 px-5 py-4 text-sm leading-relaxed text-zinc-300">
        {children}
      </div>
    </div>
  );
}

function LimitationItem({
  heading,
  body,
}: {
  heading: string;
  body: string;
}) {
  return (
    <li className="border-l-2 border-zinc-700 pl-3">
      <p className="font-medium text-zinc-200">{heading}</p>
      <p className="mt-0.5 text-xs text-zinc-400">{body}</p>
    </li>
  );
}

export default function AboutPage() {
  return (
    <div className="max-w-3xl space-y-8 pb-12">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">
          About &amp; Methodology
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          How the system works, what it measures, and what it doesn&apos;t
          claim.
        </p>
      </div>

      {/* ── What this is ───────────────────────────────────────────── */}
      <Card title="What this project is (and isn't)">
        <p>
          This is a{" "}
          <span className="font-medium text-zinc-100">portfolio project</span>{" "}
          demonstrating end-to-end ML and full-stack engineering: a Python
          ingestion + feature + model pipeline feeding a FastAPI backend and a
          Next.js dashboard.
        </p>
        <p>
          The system identifies potential pricing inefficiencies between
          DraftKings and Pinnacle on NBA games and player props, then tracks
          whether those candidate edges hold up post-game using closing line
          value (CLV).
        </p>
        <p className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-400">
          This is not financial advice, a gambling strategy, or a guaranteed
          profit system. Apparent pre-game edges routinely shrink or disappear
          under realistic execution conditions. See &ldquo;Why edges
          shrink&rdquo; below.
        </p>
      </Card>

      {/* ── Architecture ───────────────────────────────────────────── */}
      <Card title="Architecture">
        <pre className="overflow-x-auto rounded-lg bg-zinc-950 p-4 font-mono text-xs leading-snug text-zinc-400">
          {ARCH_DIAGRAM}
        </pre>
        <p className="text-xs text-zinc-500">
          The frontend never calls The Odds API or NBA Stats API directly. API
          keys live only in backend environment variables. All data flows
          through Postgres → FastAPI → browser.
        </p>
      </Card>

      {/* ── Today's Slate ──────────────────────────────────────────── */}
      <Card title="Today's Slate">
        <p>
          The Today tab shows every NBA game on the current slate alongside the
          single highest-EV candidate edge per game — if one exists and passes
          quality filters.
        </p>
        <p>
          An edge appears only when all three conditions hold: the alert is{" "}
          <span className="font-medium text-zinc-100">active</span> (not yet
          settled), it was generated within the last 6 hours, and Pinnacle
          confirms the model&apos;s direction — i.e.,{" "}
          <span className="font-mono text-xs text-zinc-300">
            pin_implied_p
          </span>{" "}
          is below the DraftKings implied probability for the same selection. If
          no alert clears those filters the card shows &ldquo;No current
          edge.&rdquo;
        </p>
        <p className="text-xs text-zinc-500">
          The page refreshes automatically every 60 seconds. Server-rendered
          data is cached for 30 seconds at the CDN edge — the first load is
          always fast even before client-side hydration.
        </p>
      </Card>

      {/* ── Data sources ───────────────────────────────────────────── */}
      <Card title="Data sources &amp; limitations">
        <div className="space-y-4">
          <div>
            <p className="font-medium text-zinc-200">
              The Odds API (DraftKings + Pinnacle)
            </p>
            <p className="mt-1 text-xs text-zinc-400">
              Polled every 5–10 minutes during the 8-hour pre-game window.
              Line movement between polls is missed — the model sees a snapshot,
              not a continuous stream. Alerts on fast-moving lines near
              tip-off may reference stale prices.
            </p>
          </div>
          <div>
            <p className="font-medium text-zinc-200">
              NBA Stats API (box scores, advanced stats)
            </p>
            <p className="mt-1 text-xs text-zinc-400">
              Synced each morning after overnight games settle. Features only
              use data from games completed before the prediction date —
              same-day post-game stats are never included. Pace, usage, and
              opponent defensive rating are rolling-window averages bounded by
              the prediction timestamp.
            </p>
          </div>
          <div>
            <p className="font-medium text-zinc-200">
              Injury reports (Rotowire RSS + NBA PDF)
            </p>
            <p className="mt-1 text-xs text-zinc-400">
              The highest-latency data source. Status polls every 30 minutes;
              a key player ruled out between polls won&apos;t affect alerts
              until the next poll cycle. Alerts generated within 30 minutes of
              a new injury filing should be treated with extra skepticism.
            </p>
          </div>
        </div>
      </Card>

      {/* ── CLV vs ROI ─────────────────────────────────────────────── */}
      <Card title="Why CLV, not ROI">
        <p>
          ROI measures win/loss outcomes, which carry very high variance over
          small samples — you need 500+ bets before it is statistically
          meaningful. A model with genuine edge can show negative ROI over a
          season through bad luck alone.
        </p>
        <p>
          <span className="font-medium text-zinc-100">
            Closing line value (CLV)
          </span>{" "}
          measures whether the bet was placed at better odds than where the
          market ultimately settled. Because sharp money drives Pinnacle&apos;s
          closing line toward true probability, consistent positive CLV is
          evidence that the model identified pricing inefficiencies before the
          market corrected them — regardless of game outcomes.
        </p>
        <p className="text-xs text-zinc-500">
          CLV is not a guarantee. It can be positive while ROI runs negative
          over bad outcome stretches. The signal also weakens for player props,
          where closing-line liquidity is shallower than for moneylines.
        </p>
      </Card>

      {/* ── Why edges shrink ───────────────────────────────────────── */}
      <Card title="Why apparent edges shrink">
        <ul className="space-y-3">
          <LimitationItem
            heading="Line movement"
            body="By the time an alert fires and a bet is placed, DraftKings may have already moved the line. The edge computed at alert time may not exist at execution time."
          />
          <LimitationItem
            heading="Vig at DraftKings"
            body="DraftKings charges roughly 5–8% juice. The modeled edge must exceed the vig to be profitable. Props carry higher vig than moneylines."
          />
          <LimitationItem
            heading="Market efficiency"
            body="Professional bettors watch the same signals. When the model identifies an edge, sharp bettors with better data and faster execution are often already there. Lines close quickly."
          />
          <LimitationItem
            heading="Model calibration drift"
            body="Calibration drifts as team compositions, coaching, pace, and injuries evolve mid-season. Walk-forward retraining partially addresses this but does not eliminate it."
          />
          <LimitationItem
            heading="Sample size"
            body="A single NBA season yields roughly 1,200 games and a few thousand props. Reliable model evaluation requires multiple seasons of walk-forward data; treat backtest results as directional signals, not precise estimates."
          />
        </ul>
      </Card>

      {/* ── Backtest methodology ───────────────────────────────────── */}
      <Card title="Backtest methodology">
        <ul className="space-y-3">
          <LimitationItem
            heading="Walk-forward training"
            body="Models are trained on seasons strictly prior to the test period. Predictions in a given season use only data from preceding seasons — no future leakage."
          />
          <LimitationItem
            heading="Point-in-time features"
            body="Every feature query is bounded by the prediction timestamp. Rest days, rolling pace, injury-adjusted lineup strength — all computed as if standing at tip-off with no knowledge of the game outcome."
          />
          <LimitationItem
            heading="Four execution scenarios"
            body="Optimistic (full edge captured at alert price), realistic (50% slippage), pessimistic (no edge captured, settled at fair value), and closing (bet placed at Pinnacle closing line). The closing scenario approximates best-case long-run CLV; realistic is the honest expectation for most bettors."
          />
          <LimitationItem
            heading="Primary metric: CLV"
            body="ROI is shown for reference. CLV per bet, averaged over a rolling window, is the headline measure of model health because it separates model skill from outcome variance."
          />
        </ul>
      </Card>

      {/* ── Tech stack ─────────────────────────────────────────────── */}
      <Card title="Tech stack">
        <div className="grid gap-x-8 gap-y-2 text-xs sm:grid-cols-2">
          {(
            [
              ["Pipeline", "Python 3.11, pandas, scikit-learn, XGBoost, SHAP"],
              ["Database", "Postgres (Supabase) + SQLAlchemy 2 + Alembic"],
              [
                "Backend",
                "FastAPI + uvicorn, sse-starlette (SSE), slowapi (rate limiting)",
              ],
              ["Frontend", "Next.js 14 App Router, TypeScript, Tailwind CSS"],
              ["Charts", "Recharts"],
              ["Data fetching", "TanStack Query v5"],
              ["Scheduling", "GitHub Actions cron"],
              ["Alerts", "Telegram bot API"],
            ] as [string, string][]
          ).map(([layer, tools]) => (
            <div key={layer} className="flex gap-2">
              <span className="w-28 shrink-0 text-zinc-500">{layer}</span>
              <span className="text-zinc-300">{tools}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* ── Builder ────────────────────────────────────────────────── */}
      <Card title="Who built this">
        <p>
          Built by{" "}
          <span className="font-medium text-zinc-100">David</span>, a software
          engineer interested in applied ML and sports analytics. This project
          was built to demonstrate a complete ML system — from raw data
          ingestion through model training, live inference, and honest result
          tracking — using a real-world domain with measurable ground truth.
        </p>
        <p className="mt-1 text-xs text-zinc-500">
          Source code:{" "}
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-emerald-500 hover:underline"
          >
            github.com/DavidMackHU
          </a>
        </p>
      </Card>
    </div>
  );
}
