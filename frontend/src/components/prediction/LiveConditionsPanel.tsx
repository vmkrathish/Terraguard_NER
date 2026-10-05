import type { RainfallCurrentResponse } from "../../types";

// Presentational only — the page fetches GET /rainfall/current (the
// data-source orchestrator: cache -> IMD -> NASA POWER reanalysis, with an
// honest insufficient_data result when nothing is available) and passes the
// result down. This is deliberately visually distinct from
// BaselineComparison/RiskTimeline, which read TerraGuard's own historical
// monthly rainfall_records — this panel is external live/reanalysis data and
// must never be mistaken for that dataset.
export default function LiveConditionsPanel({
  current,
  loading,
}: {
  current: RainfallCurrentResponse | null;
  loading: boolean;
}) {
  if (!loading && current == null) return null;

  const record = current?.record ?? null;
  const values = (record?.values as Record<string, unknown> | undefined) ?? {};
  const latest = typeof values.rainfall_mm_day_latest === "number" ? values.rainfall_mm_day_latest : null;
  const windowTotal = typeof values.rainfall_mm_total_window === "number" ? values.rainfall_mm_total_window : null;
  const sourceName = typeof record?.source_name === "string" ? record.source_name : null;
  const isCached = record?.is_cached === true;
  const observedAt = typeof record?.observed_at === "string" ? record.observed_at : null;

  return (
    <div className="card" style={{ borderStyle: "dashed" }}>
      <span className="section-label">
        <span className="live-dot" aria-hidden="true" style={{ marginRight: 6 }} />
        <span className="live-label">Live conditions (external source)</span>
      </span>

      {loading && (
        <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 8 }}>Checking live rainfall sources...</p>
      )}

      {!loading && current?.status === "insufficient_data" && (
        <p style={{ color: "var(--text-dim)", fontSize: 12.5, marginTop: 8 }}>
          Live rainfall data is not currently available for this location.
          {current.message ? ` ${current.message}` : ""}
        </p>
      )}

      {!loading && current?.status === "ok" && (
        <div style={{ marginTop: 8 }}>
          <div className="grid grid-2" style={{ marginBottom: 8 }}>
            <div className="impact-stat">
              <div className="impact-stat-value">{latest == null ? "–" : `${latest} mm/day`}</div>
              <div className="impact-stat-label">Latest live rainfall</div>
            </div>
            <div className="impact-stat">
              <div className="impact-stat-value">{windowTotal == null ? "–" : `${windowTotal} mm`}</div>
              <div className="impact-stat-label">Recent window total</div>
            </div>
          </div>
          <p style={{ fontSize: 11.5, color: "var(--text-faint)", margin: 0 }}>
            Source: {sourceName ?? "external"}
            {isCached ? " (cached)" : ""}
            {observedAt ? ` · observed ${observedAt}` : ""} — not TerraGuard's historical dataset.
          </p>
        </div>
      )}
    </div>
  );
}
