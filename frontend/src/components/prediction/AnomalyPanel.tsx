import type { EnvironmentalAnomaly } from "../../types";

// Renders the real environmental_anomaly field verbatim, including its
// mandatory disclaimer note. Handles null (artifact missing) honestly
// instead of hiding the fact that anomaly detection wasn't available.
export default function AnomalyPanel({ anomaly }: { anomaly: EnvironmentalAnomaly | null | undefined }) {
  return (
    <div className="card">
      <span className="section-label">Environmental anomaly detection</span>
      {anomaly == null ? (
        <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 8 }}>
          Anomaly detection unavailable for this prediction.
        </p>
      ) : (
        <div style={{ marginTop: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <span
              className={`badge badge-${anomaly.is_anomaly ? "CRITICAL" : "LOW"}`}
            >
              {anomaly.is_anomaly ? "Anomaly flagged" : "No anomaly flagged"}
            </span>
            <span style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
              Score: <b style={{ color: "var(--text)" }}>{anomaly.anomaly_score.toFixed(3)}</b> · Method: {anomaly.method}
            </span>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-dim)", margin: 0 }}>{anomaly.note}</p>
        </div>
      )}
    </div>
  );
}
