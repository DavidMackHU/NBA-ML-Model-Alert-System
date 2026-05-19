"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { AlertSummary } from "@/lib/types";
import { AlertCard } from "./AlertCard";
import { AlertCardSkeleton, Sk } from "./Skeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchLiveAlerts(): Promise<AlertSummary[]> {
  const res = await fetch(`${API_BASE}/api/alerts/live`);
  if (!res.ok) throw new Error("Failed to fetch live alerts");
  const body = (await res.json()) as { alerts: AlertSummary[] };
  return body.alerts;
}

function LiveBadge({ connected }: { connected: boolean }) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span
        className={`h-2 w-2 rounded-full ${
          connected ? "animate-pulse bg-emerald-500" : "bg-zinc-600"
        }`}
      />
      <span className={connected ? "text-emerald-400" : "text-zinc-500"}>
        {connected ? "Live" : "Connecting…"}
      </span>
    </div>
  );
}

export function LiveFeed() {
  const [connected, setConnected] = useState(false);
  const [sseAlerts, setSseAlerts] = useState<AlertSummary[]>([]);

  const {
    data: fetched = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["live-alerts"],
    queryFn: fetchLiveAlerts,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  useEffect(() => {
    const es = new EventSource(`${API_BASE}/api/stream/alerts`);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.addEventListener("alert", (e: MessageEvent) => {
      const incoming = JSON.parse(e.data as string) as AlertSummary;
      setSseAlerts((prev) =>
        prev.some((a) => a.id === incoming.id) ? prev : [incoming, ...prev],
      );
    });
    return () => {
      es.close();
      setConnected(false);
    };
  }, []);

  const seenIds = new Set(sseAlerts.map((a) => a.id));
  const alerts = [...sseAlerts, ...fetched.filter((a) => !seenIds.has(a.id))];

  if (isLoading) {
    return (
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-zinc-100">Candidate Edges</h2>
          <Sk className="h-4 w-12" />
        </div>
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <AlertCardSkeleton key={i} />
          ))}
        </div>
      </section>
    );
  }

  if (isError) {
    return (
      <div className="py-20 text-center text-sm text-zinc-500">
        Unable to reach the backend. Try refreshing.
      </div>
    );
  }

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-semibold text-zinc-100">Candidate Edges</h2>
        <LiveBadge connected={connected} />
      </div>
      {alerts.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 py-16 text-center">
          <p className="text-zinc-400">
            No active candidates right now — check back closer to tipoff.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {alerts.map((a) => (
            <AlertCard key={a.id} alert={a} />
          ))}
        </div>
      )}
    </section>
  );
}
