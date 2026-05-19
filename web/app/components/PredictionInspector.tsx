"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AlertDetail } from "@/lib/types";
import { Sk } from "./Skeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchAlert(id: string): Promise<AlertDetail> {
  const res = await fetch(`${API_BASE}/api/alerts/${id}`);
  if (res.status === 404) throw new Error("not_found");
  if (!res.ok) throw new Error("fetch_failed");
  return res.json() as Promise<AlertDetail>;
}

function american(price: number): string {
  return price > 0 ? `+${price}` : String(price);
}

function pct(v: number, places = 1): string {
  return `${(v * 100).toFixed(places)}%`;
}

function pp(v: number, places = 1): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(places)}pp`;
}

function tip(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

const TOOLTIP_STYLE = {
  contentStyle: {
    background: "#18181b",
    border: "1px solid #27272a",
    borderRadius: "8px",
    fontSize: 12,
  },
  labelStyle: { color: "#a1a1aa" },
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900">
      <div className="border-b border-zinc-800 px-4 py-3">
        <p className="text-sm font-medium text-zinc-300">{title}</p>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

export function PredictionInspector({ alertId }: { alertId: string }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["alert", alertId],
    queryFn: () => fetchAlert(alertId),
    staleTime: 60_000,
    retry: (_, err) => (err as Error).message !== "not_found",
  });

  if (isLoading) {
    return (
      <section className="space-y-6">
        <Sk className="h-4 w-28" />
        {[{ h: "h-40" }, { h: "h-64" }, { h: "h-32" }].map(({ h }, i) => (
          <div key={i} className="rounded-xl border border-zinc-800 bg-zinc-900">
            <div className="border-b border-zinc-800 px-4 py-3">
              <Sk className="h-3.5 w-24" />
            </div>
            <div className="p-4">
              <Sk className={h} />
            </div>
          </div>
        ))}
      </section>
    );
  }

  if (isError) {
    const is404 = (error as Error).message === "not_found";
    return (
      <div className="py-20 text-center text-sm text-zinc-500">
        {is404
          ? "Alert not found. It may have been pruned or the ID is invalid."
          : "Unable to reach the backend. Try refreshing."}
        <div className="mt-4">
          <Link href="/" className="text-emerald-500 hover:underline text-xs">
            ← Back to live alerts
          </Link>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const statusColor =
    data.status === "active"
      ? "text-emerald-400"
      : data.status === "settled"
        ? "text-zinc-400"
        : "text-zinc-500";

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-2">
        <Link href="/" className="text-xs text-zinc-500 hover:text-zinc-300">
          ← Alerts
        </Link>
        <span className="text-zinc-700">/</span>
        <span className="text-xs text-zinc-400">Inspector</span>
      </div>

      {/* ── Section 1: Alert detail ────────────────────────────────────── */}
      <Section title="Alert detail">
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs text-zinc-500 uppercase tracking-wide">
                {data.market === "h2h" ? "Moneyline" : "Player points"}
              </p>
              <p className="mt-0.5 text-lg font-semibold text-zinc-100">{data.selection}</p>
              <p className="mt-0.5 text-sm text-zinc-400">
                {data.away_team} @ {data.home_team}
              </p>
            </div>
            <div className="text-right shrink-0">
              <p className="text-2xl font-bold text-emerald-400">
                {pp(data.ev_pct, 1)}
              </p>
              <p className="text-xs text-zinc-500">modeled edge</p>
              <p className={`mt-1 text-xs font-medium ${statusColor}`}>{data.status}</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-zinc-800 p-3">
              <p className="text-xs text-zinc-500">Model P</p>
              <p className="mt-0.5 text-base font-bold text-zinc-100">{pct(data.model_p)}</p>
            </div>
            <div className="rounded-lg border border-zinc-800 p-3">
              <p className="text-xs text-zinc-500">DraftKings</p>
              <p className="mt-0.5 text-base font-bold text-zinc-100">{american(data.dk_price)}</p>
              <p className="text-xs text-zinc-600">{pct(data.dk_implied_p)} imp.</p>
            </div>
            <div className="rounded-lg border border-zinc-800 p-3">
              <p className="text-xs text-zinc-500">Pinnacle</p>
              <p className="mt-0.5 text-base font-bold text-zinc-100">{american(data.pin_price)}</p>
              <p className="text-xs text-zinc-600">{pct(data.pin_implied_p)} imp.</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-4 text-xs text-zinc-500">
            <span>
              Pin vs DK:{" "}
              <span className="font-medium text-zinc-300">{pp(data.edge_pin_vs_dk)}</span>
            </span>
            <span>
              Time to tip:{" "}
              <span className="font-medium text-zinc-300">{tip(data.time_to_tip_seconds)}</span>
            </span>
            <span>
              Alert:{" "}
              <span className="font-medium text-zinc-300">
                {new Date(data.alert_time).toLocaleString()}
              </span>
            </span>
          </div>
        </div>
      </Section>

      {/* ── Section 2: Why flagged ─────────────────────────────────────── */}
      <Section title="Why was this flagged?">
        <div className="space-y-4">
          {data.narrative && (
            <p className="text-sm text-zinc-300 leading-relaxed">{data.narrative}</p>
          )}

          {data.shap_features.length > 0 ? (
            <>
              <p className="text-xs text-zinc-500 mt-2">
                Top features by SHAP contribution (positive = raises model probability):
              </p>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    layout="vertical"
                    data={data.shap_features}
                    margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={false} />
                    <XAxis
                      type="number"
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      tickFormatter={(v) =>
                        typeof v === "number" ? `${(v * 100).toFixed(1)}pp` : ""
                      }
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={130}
                      tick={{ fill: "#a1a1aa", fontSize: 11 }}
                    />
                    <Tooltip
                      {...TOOLTIP_STYLE}
                      formatter={(value) => {
                        const v = typeof value === "number" ? value : 0;
                        return [`${(v * 100).toFixed(2)}pp`, "SHAP value"];
                      }}
                    />
                    <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                      {data.shap_features.map((f) => (
                        <Cell
                          key={f.name}
                          fill={f.value >= 0 ? "#10b981" : "#f87171"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <p className="text-xs text-zinc-600 mt-1">
              Feature importance data will appear here once the model pipeline runs SHAP
              analysis on this alert.
            </p>
          )}
        </div>
      </Section>

      {/* ── Section 3: Similar historical bets ────────────────────────── */}
      <Section title="Similar settled bets (same market)">
        {data.similar_bets.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                  <th className="pb-2 font-medium">Date</th>
                  <th className="pb-2 font-medium">Selection</th>
                  <th className="pb-2 text-right font-medium">EV%</th>
                  <th className="pb-2 text-right font-medium">Model P</th>
                  <th className="pb-2 text-right font-medium">DK</th>
                  <th className="pb-2 text-right font-medium">Outcome</th>
                  <th className="pb-2 text-right font-medium">CLV</th>
                </tr>
              </thead>
              <tbody>
                {data.similar_bets.map((sb) => {
                  const clvColor =
                    sb.clv === null
                      ? "text-zinc-500"
                      : sb.clv >= 0
                        ? "text-emerald-400"
                        : "text-red-400";
                  const outcomeColor =
                    sb.outcome === "won"
                      ? "text-emerald-400"
                      : sb.outcome === "lost"
                        ? "text-red-400"
                        : "text-zinc-500";
                  return (
                    <tr
                      key={sb.alert_id}
                      className="border-b border-zinc-800/50 last:border-0 text-zinc-300"
                    >
                      <td className="py-2.5 text-zinc-400">{sb.game_date}</td>
                      <td className="py-2.5 max-w-[140px] truncate font-medium">
                        {sb.selection}
                      </td>
                      <td className="py-2.5 text-right text-zinc-400">
                        {pp(sb.ev_pct)}
                      </td>
                      <td className="py-2.5 text-right text-zinc-400">
                        {pct(sb.model_p)}
                      </td>
                      <td className="py-2.5 text-right text-zinc-400">
                        {american(sb.dk_price)}
                      </td>
                      <td className={`py-2.5 text-right font-medium ${outcomeColor}`}>
                        {sb.outcome ?? "—"}
                      </td>
                      <td className={`py-2.5 text-right font-medium ${clvColor}`}>
                        {sb.clv !== null ? pp(sb.clv) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-4 text-center text-sm text-zinc-500">
            No settled bets for this market yet — similar situations will appear here as
            alerts are reconciled post-game.
          </p>
        )}
      </Section>
    </section>
  );
}
