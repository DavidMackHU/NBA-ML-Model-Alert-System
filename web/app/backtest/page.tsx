import type { Metadata } from "next";
import { BacktestExplorer } from "../components/BacktestExplorer";

export const metadata: Metadata = {
  title: "Backtest Explorer | NBA +EV Alert System",
  description:
    "Walk-forward backtests with point-in-time NBA data. Filter by season, market, edge threshold, and execution scenario.",
};

export default function BacktestPage() {
  return <BacktestExplorer />;
}
