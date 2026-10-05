import type { RainfallShockResponse } from "../../types";

// Presentational only — the page fetches GET /rainfall/shock (state/district/
// month change) and passes the result down, so this component can be reused
// without duplicating the fetch/debounce logic.
export default function BaselineComparison({
  shock,
  loading,
}: {
  shock: RainfallShockResponse | null;
  loading: boolean;
}) {
  return (
    <div className="card">
      <span className="section-label">Current vs. historical baseline</span>
      {loading && <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 8 }}>Loading rainfall baseline...</p>}
      {!loading && shock == null && (
        <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 8 }}>
          Rainfall baseline comparison requires a state to be selected.
        </p>
      )}
      {!loading && shock != null && (
        <div style={{ marginTop: 8 }}>
          <div className="grid grid-2" style={{ marginBottom: 10 }}>
            <div className="impact-stat">
              <div className="impact-stat-value">
                {shock.rainfall_month_actual_mm == null ? "–" : `${shock.rainfall_month_actual_mm} mm`}
              </div>
              <div className="impact-stat-label">Actual rainfall ({shock.year}-{String(shock.month).padStart(2, "0")})</div>
            </div>
            <div className="impact-stat">
              <div className="impact-stat-value">
                {shock.rainfall_month_climatology_mm == null ? "No baseline on record" : `${shock.rainfall_month_climatology_mm.toFixed(1)} mm`}
              </div>
              <div className="impact-stat-label">Climatology baseline</div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 13, marginBottom: 8 }}>
            <span>
              Departure: <b>{shock.rainfall_departure_pct == null ? "unknown" : `${shock.rainfall_departure_pct > 0 ? "+" : ""}${shock.rainfall_departure_pct.toFixed(1)}%`}</b>
            </span>
            <span>
              Consecutive wet months: <b>{shock.consecutive_wet_months ?? "unknown"}</b>
            </span>
            <span>
              Shock detected: <b style={{ color: shock.shock_detected ? "var(--critical)" : "var(--low)" }}>{shock.shock_detected ? "Yes" : "No"}</b>
            </span>
          </div>

          {shock.shock_reason && (
            <p style={{ fontSize: 12.5, color: "var(--text-dim)", margin: "0 0 6px" }}>{shock.shock_reason}</p>
          )}
          <p style={{ fontSize: 11.5, color: "var(--text-faint)", margin: 0 }}>{shock.note}</p>
        </div>
      )}
    </div>
  );
}
