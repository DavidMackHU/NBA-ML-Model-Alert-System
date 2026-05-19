import type { Metadata } from "next";
import { PredictionInspector } from "../../components/PredictionInspector";

export const metadata: Metadata = {
  title: "Alert Inspector | NBA +EV Alert System",
  description:
    "Drill into a specific alert — SHAP feature contributions, model probability, and similar historical bets.",
};

export default function AlertPage({ params }: { params: { id: string } }) {
  return <PredictionInspector alertId={params.id} />;
}
