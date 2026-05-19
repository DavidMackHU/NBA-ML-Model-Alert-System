import type { Metadata } from "next";
import { TodayClient, type TodaySlateResponse } from "./TodayClient";

export const metadata: Metadata = {
  title: "Today's Slate | NBA +EV Alert System",
  description:
    "Today's NBA games with the highest-EV candidate edge per game, updated every 60 seconds.",
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function getInitialSlate(): Promise<TodaySlateResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/today`, {
      next: { revalidate: 30 },
    });
    if (!res.ok) return null;
    return res.json() as Promise<TodaySlateResponse>;
  } catch {
    return null;
  }
}

export default async function TodayPage() {
  const initialData = await getInitialSlate();
  return <TodayClient initialData={initialData} />;
}
