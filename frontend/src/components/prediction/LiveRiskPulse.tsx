import type { RainfallShockResponse, RiskPredictResponse } from "../../types";
import RiskBadge from "../RiskBadge";

// The headline block for a real prediction result. The "Analysis timestamp"
// is honestly labeled as a client-render time (new Date()), never claimed to
// be a server timestamp — the API doesn't return one. The "elevated vs.
// baseline" line is derived only from a real /rainfall/shock response when
// one is available; with no shock data yet it says so instead of guessing.
// (Model evaluation/calibration metrics were removed from this card at the
// user's explicit request — see the Admin Dashboard removal too.)
export default function LiveRiskPulse({
  result,
  analyzedAt,
  shock,
}: {
  result: RiskPredictResponse;
  analyzedAt: Date;
  shock: RainfallShockResponse | null;
}) {
  return (
    <div className="card">
      <span className="section-label">Live risk pulse</span>
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 6, marginBottom: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 36, fontWeight: 800 }}>{result.risk_score}</span>
        <RiskBadge level={result.risk_level} />
        <span style={{ color: "var(--text-dim)", fontSize: 13 }}>
          Probability: <b>{(result.probability * 100).toFixed(1)}%</b>
        </span>
      </div>

      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 12.5, color: "var(--text-dim)", marginBottom: 10 }}>
        <span>Model: <b style={{ color: "var(--text)" }}>{result.model_version}</b></span>
        <span>Explainability: <b style={{ color: "var(--text)" }}>{result.explainability_method}</b></span>
        <span>Analysis timestamp (this device): <b style={{ color: "var(--text)" }}>{analyzedAt.toLocaleString()}</b></span>
      </div>

      <div style={{ padding: "10px 12px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)", fontSize: 13 }}>
        {shock == null ? (
          <span style={{ color: "var(--text-dim)" }}>Rainfall baseline comparison not yet available for this query.</span>
        ) : shock.rainfall_departure_pct == null ? (
          <span style={{ color: "var(--text-dim)" }}>No climatology baseline on record for {shock.state}{shock.district ? ` / ${shock.district}` : ""} — cannot say whether rainfall is elevated.</span>
        ) : (
          <span>
            {shock.shock_detected ? "⚠ " : ""}
            Rainfall is <b style={{ color: shock.rainfall_departure_pct > 0 ? "var(--critical)" : "var(--low)" }}>
              {shock.rainfall_departure_pct > 0 ? "+" : ""}{shock.rainfall_departure_pct.toFixed(1)}%
            </b> vs. the seasonal climatology baseline
            {shock.shock_detected ? " — flagged as a rainfall shock" : " — within/below the shock threshold"}.
          </span>
        )}
      </div>
    </div>
  );
}
