"use client";

import { useQuery } from "@tanstack/react-query";
import { GameCard } from "./GameCard";
import { Sk } from "../components/Skeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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

export interface TodaySlateResponse {
  slate_date: string;
  games: TodayGame[];
  generated_at: string;
}

async function fetchTodaySlate(): Promise<TodaySlateResponse> {
  const res = await fetch(`${API_BASE}/api/today`);
  if (!res.ok) throw new Error("Failed to fetch today's slate");
  return res.json() as Promise<TodaySlateResponse>;
}

function GameCardSkeleton() {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <Sk className="h-4 w-48" />
        <Sk className="h-3 w-16" />
      </div>
      <div className="px-4 py-3 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1.5">
            <Sk className="h-4 w-40" />
            <Sk className="h-3 w-32" />
          </div>
          <Sk className="h-5 w-16" />
        </div>
      </div>
    </div>
  );
}

function formatSlateDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "America/New_York",
  });
}

export function TodayClient({
  initialData,
}: {
  initialData: TodaySlateResponse | null;
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["today-slate"],
    queryFn: fetchTodaySlate,
    refetchInterval: 60_000,
    staleTime: 30_000,
    initialData: initialData ?? undefined,
  });

  if (isLoading && !data) {
    return (
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-zinc-100">Today&apos;s Slate</h2>
          <Sk className="h-3 w-24" />
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3].map((i) => (
            <GameCardSkeleton key={i} />
          ))}
        </div>
      </section>
    );
  }

  if (isError && !data) {
    return (
      <div className="py-20 text-center text-sm text-zinc-500">
        Unable to reach the backend. Try refreshing.
      </div>
    );
  }

  const games = data?.games ?? [];

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-semibold text-zinc-100">Today&apos;s Slate</h2>
        {data && (
          <span className="text-xs text-zinc-500">
            {formatSlateDate(data.slate_date)}
          </span>
        )}
      </div>
      {games.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 py-16 text-center">
          <p className="text-zinc-400">No games on the slate today.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {games.map((game) => (
            <GameCard key={game.game_id} game={game} />
          ))}
        </div>
      )}
    </section>
  );
}
