import { useDashboardData } from "../../hooks/useDashboardData";
import { DashboardError, DashboardLoading } from "../../components/DashboardStates";
import RiskBadge from "../../components/RiskBadge";
import ProvenanceTag from "../../components/ProvenanceTag";
import StatusBadge from "../../components/StatusBadge";
import LiveWeatherCarousel from "../../components/LiveWeatherCarousel";

// Authority view: command-center oversight across the whole covered region —
// counts, active alerts, blocked infrastructure, and the full risk-zone
// table. This is the closest to the original shared DashboardPage, kept as
// the default landing view for anyone coordinating a response rather than
// working one site or administering the system.
export default function AuthorityDashboardPage() {
  const { layers, alerts, reports, error, loading } = useDashboardData();

  if (error) return <DashboardError error={error} />;
  if (loading || !layers) return <DashboardLoading />;

  const criticalZones = layers.risk_zones.filter((z) => z.risk_level === "CRITICAL" || z.risk_level === "HIGH");
  const blockedRoads = layers.roads.filter((r) => r.status === "blocked");
  const pendingReports = reports.filter((r) => r.sync_status !== "synced");

  return (
    <div className="fade-in-up authority-dashboard">
      <div className="page-header">
        <div>
          <h2 className="page-title">Authority Dashboard</h2>
          <p className="page-subtitle">
            Region-wide early warning overview. Predict → Detect → Assess Impact → Explain → Find Safe Route → Report → Warn.
          </p>
        </div>
      </div>

      <div className="grid grid-3">
        <div className="card stat-tile admin-stat-tile">
          <span className="icon-chip">⛰</span>
          <div className="value">{layers.landslide_events.length}</div>
          <div className="label">Historical landslide events</div>
        </div>
        <div className="card stat-tile admin-stat-tile">
          <span className="icon-chip">⚠</span>
          <div className="value">{criticalZones.length}</div>
          <div className="label">High / critical risk zones</div>
        </div>
        <div className="card stat-tile admin-stat-tile">
          <span className="icon-chip">🛣</span>
          <div className="value">{blockedRoads.length}</div>
          <div className="label">Blocked road segments</div>
        </div>
      </div>

      <div className="grid grid-2">
        {/* System status was removed here at the user's request — replaced
            with the live weather-by-state carousel below. */}
        <LiveWeatherCarousel />

        {/* Item 10: separate alert cards instead of a single-line table —
            not present in the reference zip for this exact page, built
            directly from the user's own description. */}
        <div className="card admin-panel-card">
          <h3>Recent alerts</h3>
          {alerts.length === 0 && <p className="table-empty">No alerts yet. Try the Alerts page test interface.</p>}
          {alerts.length > 0 && (
            <div className="alert-card-grid">
              {alerts.map((a) => (
                <div key={a.id} className="alert-card">
                  <RiskBadge level={a.severity} />
                  <div className="alert-card-type">{a.alert_type}</div>
                  <div className="alert-card-reason">{a.reason}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card admin-panel-card">
        <h3>Risk zone summary</h3>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Zone</th><th>Risk level</th><th>Score</th><th>Provenance</th></tr></thead>
            <tbody>
              {layers.risk_zones.map((z) => (
                <tr key={z.id}>
                  <td>{z.name}</td>
                  <td><RiskBadge level={z.risk_level} /></td>
                  <td>{z.risk_score}</td>
                  <td><ProvenanceTag provenance={z.data_provenance} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {pendingReports.length > 0 && (
        <div className="card admin-panel-card">
          <h3>Pending field reports</h3>
          <p style={{ marginBottom: 0 }}>
            <StatusBadge status="pending" /> {pendingReports.length} report(s) awaiting sync.
          </p>
        </div>
      )}
    </div>
  );
}
