import Link from "next/link";
import { Clock, TrendingUp, Minus } from "lucide-react";

interface BestEdge {
  alert_id: string;
  market: string;
  selection: string;
  ev_pct: number;
  model_p: number;
  dk_implied_p: number;
  pin_implied_p: number;
  dk_price: number;
  pin_price: number;
}

interface TodayGame {
  game_id: number;
  home_team: string;
  away_team: string;
  tipoff_utc: string;
  tipoff_local_et: string;
  status: string;
  home_score: number | null;
  away_score: number | null;
  best_edge: BestEdge | null;
}

function formatTipoff(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  });
}

function formatOdds(price: number): string {
  return price > 0 ? `+${price}` : String(price);
}

function EvBadge({ ev_pct }: { ev_pct: number }) {
  const pct = ev_pct * 100;
  const color =
    pct >= 5
      ? "bg-emerald-900 text-emerald-300 border-emerald-700"
      : pct >= 3
        ? "bg-yellow-900 text-yellow-300 border-yellow-700"
        : "bg-zinc-800 text-zinc-400 border-zinc-700";
  return (
    <span
      className={`rounded border px-2 py-0.5 text-xs font-semibold ${color}`}
    >
      EV {pct.toFixed(1)}%
    </span>
  );
}

function Scoreline({ game }: { game: TodayGame }) {
  if (game.status === "final") {
    return (
      <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        Final {game.away_score}–{game.home_score}
      </span>
    );
  }
  if (game.status === "live") {
    return (
      <span className="text-xs font-medium uppercase tracking-wide text-emerald-400">
        Live {game.away_score}–{game.home_score}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-xs text-zinc-500">
      <Clock className="h-3 w-3" />
      {formatTipoff(game.tipoff_local_et)}
    </span>
  );
}

export function GameCard({ game }: { game: TodayGame }) {
  const dimmed = game.status === "final";

  return (
    <div
      className={`rounded-xl border border-zinc-800 bg-zinc-900 transition-opacity ${dimmed ? "opacity-60" : ""}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <span className="text-sm font-semibold text-zinc-100">
          {game.away_team} @ {game.home_team}
        </span>
        <Scoreline game={game} />
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {game.best_edge ? (
          <div className="space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <TrendingUp className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                <div>
                  <p className="text-sm font-medium text-zinc-100">
                    {game.best_edge.selection}
                    {" "}
                    <span className="font-mono text-zinc-300">
                      {formatOdds(game.best_edge.dk_price)}
                    </span>
                  </p>
                  <p className="mt-0.5 text-xs text-zinc-500">
                    Model {(game.best_edge.model_p * 100).toFixed(0)}%
                    {" · "}
                    DK {(game.best_edge.dk_implied_p * 100).toFixed(0)}%
                    {" · "}
                    Pin {(game.best_edge.pin_implied_p * 100).toFixed(0)}%
                  </p>
                </div>
              </div>
              <EvBadge ev_pct={game.best_edge.ev_pct} />
            </div>
            <div className="flex justify-end">
              <Link
                href={`/alerts/${game.best_edge.alert_id}`}
                className="text-xs text-emerald-500 hover:underline"
              >
                Inspect →
              </Link>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-zinc-600">
            <Minus className="h-3.5 w-3.5 shrink-0" />
            <div>
              <p className="text-sm">No current edge</p>
              <p className="text-xs">Model agrees with DraftKings</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
