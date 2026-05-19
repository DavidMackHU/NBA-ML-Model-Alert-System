import Link from "next/link";
import type { AlertSummary } from "@/lib/types";

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

function american(v: number) {
  return v > 0 ? `+${v}` : String(v);
}

function tip(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export function AlertCard({ alert }: { alert: AlertSummary }) {
  const evSign = alert.ev_pct > 0 ? "+" : "";
  return (
    <Link
      href={`/alerts/${alert.id}`}
      className="block rounded-xl border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-600 transition-colors"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-zinc-500">{alert.market}</p>
          <p className="truncate font-semibold text-zinc-100">{alert.selection}</p>
          <p className="text-sm text-zinc-400">
            {alert.away_team} @ {alert.home_team}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-xl font-bold text-emerald-400">
            {evSign}{pct(alert.ev_pct)}
          </p>
          <p className="text-xs text-zinc-500">{tip(alert.time_to_tip_seconds)} to tip</p>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 divide-x divide-zinc-800 text-center text-xs">
        <div className="px-2">
          <p className="text-zinc-500">Model P</p>
          <p className="font-medium text-zinc-200">{pct(alert.model_p)}</p>
        </div>
        <div className="px-2">
          <p className="text-zinc-500">DK</p>
          <p className="font-medium text-zinc-200">
            {american(alert.dk_price)}{" "}
            <span className="text-zinc-400">({pct(alert.dk_implied_p)})</span>
          </p>
        </div>
        <div className="px-2">
          <p className="text-zinc-500">Pin</p>
          <p className="font-medium text-zinc-200">
            {american(alert.pin_price)}{" "}
            <span className="text-zinc-400">({pct(alert.pin_implied_p)})</span>
          </p>
        </div>
      </div>
    </Link>
  );
}
