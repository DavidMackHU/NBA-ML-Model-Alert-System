import type { Metadata } from "next";
import { LiveFeed } from "../components/LiveFeed";

export const metadata: Metadata = {
  title: "Live Alerts | NBA +EV Alert System",
  description:
    "Real-time NBA candidate edge alerts — moneyline and player props where model probability diverges from market pricing.",
};

export default function AlertsPage() {
  return <LiveFeed />;
}
