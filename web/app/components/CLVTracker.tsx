"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CLVResponse } from "@/lib/types";
import { ChartSkeleton, StatCardSkeleton } from "./Skeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchCLV(days: number): Promise<CLVResponse> {
  const res = await fetch(`${API_BASE}/api/clv?days=${days}`);
  if (!res.ok) throw new Error("Failed to fetch CLV data");
  return res.json() as Promise<CLVResponse>;
}

function pp(v: number, places = 1) {
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(places)}pp`;
}

function StatCard({ label, value, dim = false }: { label: string; value: string; dim?: boolean }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className={`mt-1 text-xl font-bold ${dim ? "text-zinc-400" : "text-zinc-100"}`}>{value}</p>
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

export function CLVTracker() {
  const [days, setDays] = useState<30 | 90>(30);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["clv", days],
    queryFn: () => fetchCLV(days),
    staleTime: 60_000,
  });

  return (
    <section className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold text-zinc-100">CLV Tracker</h2>
          <p className="mt-1 text-xs text-zinc-500">
            CLV measures whether bets beat the closing market price — not realized profit.
          </p>
        </div>
        <div className="flex shrink-0 gap-1 rounded-lg border border-zinc-800 p-1 text-xs">
          {([30, 90] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`rounded-md px-3 py-1 transition-colors ${
                days === d
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-400 hover:text-zinc-100"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <StatCardSkeleton key={i} />
            ))}
          </div>
          <ChartSkeleton />
        </>
      )}

      {isError && (
        <div className="py-20 text-center text-sm text-zinc-500">
          Unable to reach the backend. Try refreshing.
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Mean CLV" value={pp(data.mean_clv)} />
            <StatCard label="Model EV" value={pp(data.mean_ev)} />
            <StatCard
              label={`ROI (${data.n_settled} settled)`}
              value={pp(data.roi)}
              dim={data.n_settled === 0}
            />
            <StatCard
              label="Win Rate"
              value={data.n_settled > 0 ? `${(data.win_rate * 100).toFixed(0)}%` : "—"}
              dim={data.n_settled === 0}
            />
          </div>

          {data.daily.length > 0 ? (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <p className="mb-4 text-sm font-medium text-zinc-300">
                Cumulative CLV over time — last {days} days
              </p>
              <div className="h-60">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={data.daily}
                    margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      tickFormatter={(v) =>
                        typeof v === "string" ? v.slice(5) : String(v)
                      }
                    />
                    <YAxis
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      tickFormatter={(v) =>
                        typeof v === "number" ? `${(v * 100).toFixed(1)}pp` : ""
                      }
                    />
                    <Tooltip
                      {...TOOLTIP_STYLE}
                      formatter={(value, name) => {
                        const v = typeof value === "number" ? value : 0;
                        const label =
                          name === "cumulative_clv" ? "Realized CLV" : "Model EV";
                        return [`${(v * 100).toFixed(2)}pp`, label];
                      }}
                    />
                    <Legend
                      formatter={(v) =>
                        v === "cumulative_clv" ? "Realized CLV" : "Model EV"
                      }
                      wrapperStyle={{ color: "#a1a1aa", fontSize: 12 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="cumulative_clv"
                      stroke="#10b981"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="cumulative_ev"
                      stroke="#818cf8"
                      strokeWidth={2}
                      strokeDasharray="4 4"
                      dot={false}
                      activeDot={{ r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-zinc-600">
                Running mean. Model EV (dashed) = modeled edge at alert time; Realized CLV = actual
                closing-line value.
              </p>
            </div>
          ) : (
            <div className="rounded-xl border border-zinc-800 py-10 text-center text-sm text-zinc-500">
              No settled bets in the last {days} days — chart will appear once bets are reconciled.
            </div>
          )}

          {data.by_market.length > 0 && (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900">
              <div className="border-b border-zinc-800 px-4 py-3">
                <p className="text-sm font-medium text-zinc-300">Breakdown by market</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                      <th className="px-4 py-2 font-medium">Market</th>
                      <th className="px-4 py-2 text-right font-medium">Bets</th>
                      <th className="px-4 py-2 text-right font-medium">Settled</th>
                      <th className="px-4 py-2 text-right font-medium">Mean CLV</th>
                      <th className="px-4 py-2 text-right font-medium">Model EV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_market.map((row) => (
                      <tr
                        key={row.market}
                        className="border-b border-zinc-800/50 last:border-0 text-zinc-300"
                      >
                        <td className="px-4 py-2.5 font-medium">{row.market}</td>
                        <td className="px-4 py-2.5 text-right text-zinc-400">{row.n_bets}</td>
                        <td className="px-4 py-2.5 text-right text-zinc-400">{row.n_settled}</td>
                        <td
                          className={`px-4 py-2.5 text-right font-medium ${
                            row.mean_clv >= 0 ? "text-emerald-400" : "text-red-400"
                          }`}
                        >
                          {pp(row.mean_clv)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-indigo-400">
                          {pp(row.mean_ev)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
