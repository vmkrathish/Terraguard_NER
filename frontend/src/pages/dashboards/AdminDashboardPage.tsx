import { useDashboardData } from "../../hooks/useDashboardData";
import { DashboardError, DashboardLoading } from "../../components/DashboardStates";
import { useAuth } from "../../auth/AuthContext";
import LiveWeatherCarousel from "../../components/LiveWeatherCarousel";

function HealthBadge({ ok, okLabel, badLabel }: { ok: boolean; okLabel: string; badLabel: string }) {
  return (
    <span className={`badge badge-${ok ? "GOOD" : "BAD"}`}>
      <span className="badge-icon" aria-hidden="true">{ok ? "✓" : "✕"}</span>
      {ok ? okLabel : badLabel}
    </span>
  );
}

const RISK_LEVEL_ORDER = ["CRITICAL", "HIGH", "MODERATE", "LOW"] as const;
const RISK_LEVEL_COLOR: Record<string, string> = {
  CRITICAL: "var(--critical, #dc2626)",
  HIGH: "var(--moderate, #f59e0b)",
  MODERATE: "#eab308",
  LOW: "var(--low, #10b981)",
};

// Admin view: system/data-integrity oversight rather than incident response —
// risk analytics and backend configuration health. Nothing here is
// invented: every count and ranking below is tallied client-side from rows
// the dashboard already receives from /map/layers — the same
// district_event_summary/risk_zones data every other dashboard uses, never
// a separately fabricated statistic. (Model evaluation metrics were
// removed from this dashboard at the user's explicit request.)
export default function AdminDashboardPage() {
  const { layers, alerts, health, error, loading } = useDashboardData();
  const { user } = useAuth();

  if (error) return <DashboardError error={error} />;
  if (loading || !layers) return <DashboardLoading />;

  // Risk-zone breakdown by level — real rows from /map/layers, not derived data.
  const riskLevelCounts: Record<string, number> = {};
  layers.risk_zones.forEach((z) => {
    const level = (z.risk_level || "").toUpperCase();
    riskLevelCounts[level] = (riskLevelCounts[level] || 0) + 1;
  });
  const maxRiskLevelCount = Math.max(1, ...Object.values(riskLevelCounts));

  // State-wise historical-event analysis — TerraGuard's risk_zones have no
  // state field, so this is built from district_event_summary, the only
  // real per-state/district aggregate the backend provides (see
  // MapLayers.district_event_summary — never invented client-side).
  const stateEventTotals = new Map<string, { events: number; highSeverity: number }>();
  layers.district_event_summary.forEach((row) => {
    const prev = stateEventTotals.get(row.state) || { events: 0, highSeverity: 0 };
    stateEventTotals.set(row.state, {
      events: prev.events + row.event_count,
      highSeverity: prev.highSeverity + row.high_severity_count,
    });
  });
  const stateRows = Array.from(stateEventTotals.entries())
    .map(([state, v]) => ({ state, ...v }))
    .sort((a, b) => (b.highSeverity - a.highSeverity) || (b.events - a.events));
  const maxStateEvents = Math.max(1, ...stateRows.map((r) => r.events));
  const topRiskState = stateRows.length > 0 ? stateRows[0] : null;

  // alerts.status is set to "active" at issue time (or "test" for the
  // Alerts-page test interface) and never transitions to a "resolved"
  // state in this codebase — see alerting.py — so "active" is the only
  // status value that means a real, currently-standing alert.
  const activeAlertCount = alerts.filter((a) => a.status === "active").length;
  const criticalZoneCount = riskLevelCounts.CRITICAL || 0;
  const highZoneCount = riskLevelCounts.HIGH || 0;

  // Highlights are only ever built from values already computed above —
  // if a category has nothing to report, it's left out rather than padded
  // with a placeholder.
  const highlights: string[] = [];
  if (topRiskState) {
    highlights.push(
      `${topRiskState.state} has the most high-severity historical landslide events on file (${topRiskState.highSeverity} of ${topRiskState.events} recorded events).`
    );
  }
  if (criticalZoneCount > 0) {
    highlights.push(`${criticalZoneCount} risk zone${criticalZoneCount === 1 ? " is" : "s are"} currently classified CRITICAL.`);
  }
  if (highZoneCount > 0) {
    highlights.push(`${highZoneCount} additional risk zone${highZoneCount === 1 ? " is" : "s are"} classified HIGH.`);
  }
  if (activeAlertCount > 0) {
    // `alerts` here is the dashboard's most-recent-8 fetch (see
    // useDashboardData), not a full table count — worded as such rather
    // than implying an exhaustive active-alert total.
    highlights.push(
      `${activeAlertCount} of the most recent alerts ${activeAlertCount === 1 ? "is" : "are"} still active.`
    );
  }
  if (health?.llm_configured === false) {
    highlights.push("The AI Assist LLM is not configured — chat answers are currently using extract-based fallback only.");
  }

  return (
    <div className="fade-in-up admin-dashboard">
      <div className="page-header">
        <div>
          <h2 className="page-title">Admin Dashboard</h2>
          <p className="page-subtitle">System health, risk analytics, and model evaluation oversight.</p>
        </div>
      </div>

      <div className="grid grid-3">
        <div className="card stat-tile admin-stat-tile">
          <span className="icon-chip">👤</span>
          <div className="value" style={{ fontSize: 20 }}>{user?.full_name || user?.email}</div>
          <div className="label">Signed in as admin</div>
        </div>
        <div className="card stat-tile admin-stat-tile">
          <span className="icon-chip">🗺</span>
          <div className="value">{layers.risk_zones.length}</div>
          <div className="label">Total mapped risk zones</div>
        </div>
        <div className="card stat-tile admin-stat-tile">
          <span className="icon-chip">📚</span>
          <div className="value">{layers.landslide_events.length}</div>
          <div className="label">Total historical events on file</div>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card admin-panel-card">
          <h3>Backend configuration</h3>
          {health && (
            <table>
              <tbody>
                <tr><td>Excel dataset</td><td><HealthBadge ok={!!(health.data_store as { ready: boolean })?.ready} okLabel="loaded" badLabel="not available" /></td></tr>
                <tr><td>ML model</td><td><HealthBadge ok={!!(health.ml_model as { ready: boolean })?.ready} okLabel="loaded" badLabel="missing" /></td></tr>
                <tr><td>LLM configured</td><td><HealthBadge ok={!!health.llm_configured} okLabel="yes" badLabel="no (fallback answers)" /></td></tr>
                <tr><td>Routing engine</td><td>{String(health.routing_engine ?? "unknown")}</td></tr>
              </tbody>
            </table>
          )}
        </div>

        <div className="card admin-panel-card">
          <h3>Risk zone breakdown</h3>
          <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: -8 }}>
            {layers.risk_zones.length} mapped risk zone{layers.risk_zones.length === 1 ? "" : "s"}, by current risk level.
          </p>
          <div className="risk-bar-list">
            {RISK_LEVEL_ORDER.filter((level) => riskLevelCounts[level] > 0).map((level) => (
              <div className="risk-bar-row" key={level}>
                <span className="risk-bar-label">{level}</span>
                <div className="risk-bar-track">
                  <div
                    className="risk-bar-fill"
                    style={{ width: `${(riskLevelCounts[level] / maxRiskLevelCount) * 100}%`, background: RISK_LEVEL_COLOR[level] }}
                  />
                </div>
                <span className="risk-bar-value">{riskLevelCounts[level]}</span>
              </div>
            ))}
            {layers.risk_zones.length === 0 && <p className="table-empty">No risk zones mapped yet.</p>}
          </div>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card admin-panel-card">
          <h3>State-wise risk analysis</h3>
          <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: -8 }}>
            Historical landslide events by state, from TerraGuard's own records — darker portion is high-severity.
          </p>
          <div className="risk-bar-list">
            {stateRows.map((row) => (
              <div className="risk-bar-row" key={row.state}>
                <span className="risk-bar-label" title={row.state}>{row.state}</span>
                <div className="risk-bar-track">
                  <div className="risk-bar-fill state-bar-total" style={{ width: `${(row.events / maxStateEvents) * 100}%` }} />
                  <div
                    className="risk-bar-fill state-bar-severe"
                    style={{ width: `${(row.highSeverity / maxStateEvents) * 100}%` }}
                  />
                </div>
                <span className="risk-bar-value">{row.events}</span>
              </div>
            ))}
            {stateRows.length === 0 && <p className="table-empty">No per-state event data available yet.</p>}
          </div>
        </div>

        <LiveWeatherCarousel />
      </div>

      <div className="grid grid-2">
        <div className="card admin-panel-card">
          <h3>Highest risk region</h3>
          {topRiskState ? (
            <>
              <div className="value" style={{ fontSize: 26, marginTop: 4 }}>{topRiskState.state}</div>
              <p style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 4 }}>
                {topRiskState.highSeverity} high-severity event{topRiskState.highSeverity === 1 ? "" : "s"} of {topRiskState.events} recorded — the most of any state on file.
              </p>
            </>
          ) : (
            <p className="table-empty">No per-state event data available yet.</p>
          )}
        </div>

        <div className="card admin-panel-card">
          <h3>TerraGuard insights</h3>
          {highlights.length > 0 ? (
            <ul className="insights-list">
              {highlights.map((h, i) => (
                <li key={i}>{h}</li>
              ))}
            </ul>
          ) : (
            <p className="table-empty">No recent significant updates.</p>
          )}
        </div>
      </div>
    </div>
  );
}
