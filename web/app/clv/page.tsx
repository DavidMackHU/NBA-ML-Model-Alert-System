import type { Metadata } from "next";
import { CLVTracker } from "../components/CLVTracker";

export const metadata: Metadata = {
  title: "CLV Tracker | NBA +EV Alert System",
  description:
    "Track realized closing line value vs modeled edge over rolling 30 and 90 day windows.",
};

export default function CLVPage() {
  return <CLVTracker />;
}
