import type { RainfallShockResponse, RiskPredictResponse } from "../../types";

// A deterministic, template-built one-paragraph summary — NOT an LLM call.
// Every clause is gated on a real field from the prediction response (or the
// real /rainfall/shock response); nothing here is generated or inferred
// beyond simple string templating on values that are already in hand.
export default function GroundedCaption({
  result,
  shock,
}: {
  result: RiskPredictResponse;
  shock: RainfallShockResponse | null;
}) {
  const elevated = result.risk_level === "CRITICAL" || result.risk_level === "HIGH";
  const sentences: string[] = [
    `${elevated ? "Elevated" : "Low-to-moderate"} landslide risk detected for the selected location (risk level ${result.risk_level}).`,
  ];

  if (shock?.rainfall_departure_pct != null) {
    sentences.push(
      shock.rainfall_departure_pct > 0
        ? `Rainfall for this period is running ${shock.rainfall_departure_pct.toFixed(1)}% above the seasonal climatology baseline${shock.shock_detected ? ", enough to be flagged as a rainfall shock" : ""}.`
        : `Rainfall for this period is running ${Math.abs(shock.rainfall_departure_pct).toFixed(1)}% below the seasonal climatology baseline.`,
    );
  }

  const histCount = result.rainfall_context?.["historical_landslide_count_20km"];
  if (typeof histCount === "number") {
    sentences.push(
      histCount > 0
        ? `${histCount} historical landslide event${histCount === 1 ? "" : "s"} on record within 20km of this point.`
        : "No historical landslide events on record within 20km of this point.",
    );
  }

  if (result.environmental_anomaly) {
    sentences.push(
      result.environmental_anomaly.is_anomaly
        ? "This combination of rainfall/historical-activity features is statistically unusual relative to the training data (flagged as an anomaly)."
        : "This combination of rainfall/historical-activity features is not statistically unusual relative to the training data.",
    );
  }

  return (
    <p style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--text)", background: "var(--surface-2)", padding: "10px 12px", borderRadius: "var(--radius-sm)", margin: "0 0 var(--sp-3)" }}>
      {sentences.join(" ")}
    </p>
  );
}
