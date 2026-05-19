"use client";
import { useState } from "react";
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
import type { BacktestResponse } from "@/lib/types";
import { ChartSkeleton, StatCardSkeleton } from "./Skeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const SCENARIO_LABELS: Record<string, string> = {
  perfect: "Perfect execution",
  tick_worse: "1 tick worse",
  unavailable_20pct: "20% unavailable",
  limit_after_200: "$100 limit after 200",
};

const SEASONS = [2021, 2022, 2023, 2024, 2025];
const SCENARIOS = ["perfect", "tick_worse", "unavailable_20pct", "limit_after_200"] as const;

async function fetchBacktest(
  season: number | null,
  market: string,
  threshold: number,
  scenario: string,
): Promise<BacktestResponse> {
  const params = new URLSearchParams({ market, threshold: threshold.toString(), scenario });
  if (season !== null) params.set("season", season.toString());
  const res = await fetch(`${API_BASE}/api/backtest?${params}`);
  if (!res.ok) throw new Error("Failed to fetch backtest data");
  return res.json() as Promise<BacktestResponse>;
}

function pp(v: number, places = 1) {
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(places)}pp`;
}

function pct(v: number, places = 1) {
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(places)}%`;
}

function StatCard({
  label,
  value,
  dim = false,
}: {
  label: string;
  value: string;
  dim?: boolean;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className={`mt-1 text-xl font-bold ${dim ? "text-zinc-400" : "text-zinc-100"}`}>
        {value}
      </p>
    </div>
  );
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

export function BacktestExplorer() {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [season, setSeason] = useState<number | null>(null);
  const [market, setMarket] = useState("h2h");
  const [threshold, setThreshold] = useState(0.03);
  const [scenario, setScenario] = useState("perfect");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["backtest", season, market, threshold, scenario],
    queryFn: () => fetchBacktest(season, market, threshold, scenario),
    staleTime: 60_000,
  });

  const selectClass =
    "w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-emerald-500";

  const filtersPanel = (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div className="space-y-1.5">
        <label className="text-xs text-zinc-500">Season</label>
        <select
          value={season ?? ""}
          onChange={(e) => setSeason(e.target.value ? Number(e.target.value) : null)}
          className={selectClass}
        >
          <option value="">All seasons</option>
          {SEASONS.map((s) => (
            <option key={s} value={s}>
              {s - 1}–{s}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <label className="text-xs text-zinc-500">Market</label>
        <select
          value={market}
          onChange={(e) => setMarket(e.target.value)}
          className={selectClass}
        >
          <option value="h2h">Moneyline (h2h)</option>
          <option value="player_points">Player points</option>
        </select>
      </div>

      <div className="space-y-1.5">
        <label className="text-xs text-zinc-500">
          Edge threshold — {(threshold * 100).toFixed(1)}%
        </label>
        <input
          type="range"
          min="0.01"
          max="0.10"
          step="0.005"
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          className="w-full accent-emerald-500"
        />
        <div className="flex justify-between text-xs text-zinc-600">
          <span>1%</span>
          <span>10%</span>
        </div>
      </div>

      <div className="space-y-1.5">
        <label className="text-xs text-zinc-500">Execution scenario</label>
        <select
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          className={selectClass}
        >
          {SCENARIOS.map((sc) => (
            <option key={sc} value={sc}>
              {SCENARIO_LABELS[sc]}
            </option>
          ))}
        </select>
      </div>
    </div>
  );

  return (
    <section className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold text-zinc-100">Backtest Explorer</h2>
          <p className="mt-1 text-xs text-zinc-500">
            Walk-forward backtest with point-in-time data. CLV vs Pinnacle close is the
            primary metric — not ROI.
          </p>
        </div>
        <button
          onClick={() => setFiltersOpen((o) => !o)}
          className="shrink-0 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-100 sm:hidden"
        >
          {filtersOpen ? "Hide filters" : "Filters"}
        </button>
      </div>

      <div
        className={`rounded-xl border border-zinc-800 bg-zinc-900 p-4 ${
          filtersOpen ? "block" : "hidden sm:block"
        }`}
      >
        {filtersPanel}
      </div>

      {isLoading && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <StatCardSkeleton key={i} />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <ChartSkeleton className="h-52" />
            <ChartSkeleton className="h-52" />
          </div>
        </>
      )}

      {isError && (
        <div className="py-20 text-center text-sm text-zinc-500">
          Unable to reach the backend. Try refreshing.
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard
              label={`Bets (${data.n_settled} settled)`}
              value={String(data.n_bets)}
              dim={data.n_bets === 0}
            />
            <StatCard label="Mean CLV" value={pp(data.mean_clv)} />
            <StatCard label="ROI" value={pct(data.roi)} />
            <StatCard
              label="Hit rate"
              value={data.n_settled > 0 ? `${(data.hit_rate * 100).toFixed(0)}%` : "—"}
              dim={data.n_settled === 0}
            />
            <StatCard
              label="Brier score"
              value={data.n_settled > 0 ? data.brier_score.toFixed(3) : "—"}
              dim={data.n_settled === 0}
            />
          </div>

          {data.n_bets > 0 ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                <p className="mb-4 text-sm font-medium text-zinc-300">
                  Edge size distribution
                </p>
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={data.edge_distribution}
                      margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="label" tick={{ fill: "#71717a", fontSize: 11 }} />
                      <YAxis
                        tick={{ fill: "#71717a", fontSize: 11 }}
                        allowDecimals={false}
                      />
                      <Tooltip
                        {...TOOLTIP_STYLE}
                        formatter={(value, name) => {
                          if (name === "n_bets") return [value, "Bets"];
                          return [value, String(name)];
                        }}
                      />
                      <Bar dataKey="n_bets" fill="#10b981" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-xs text-zinc-600">
                  Count of qualifying bets per modeled-edge bucket.
                </p>
              </div>

              <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                <p className="mb-4 text-sm font-medium text-zinc-300">
                  CLV outcome distribution
                </p>
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={data.clv_distribution}
                      margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="label" tick={{ fill: "#71717a", fontSize: 11 }} />
                      <YAxis
                        tick={{ fill: "#71717a", fontSize: 11 }}
                        allowDecimals={false}
                      />
                      <Tooltip
                        {...TOOLTIP_STYLE}
                        formatter={(value) => [value, "Settled bets"]}
                      />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {data.clv_distribution.map((entry, i) => (
                          <Cell key={entry.label} fill={i >= 2 ? "#10b981" : "#f87171"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-xs text-zinc-600">
                  Settled bets by realized CLV vs Pinnacle closing line.
                </p>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-zinc-800 py-10 text-center text-sm text-zinc-500">
              No bets matched these filters — try lowering the edge threshold or selecting
              a different season.
            </div>
          )}
        </>
      )}
    </section>
  );
}
