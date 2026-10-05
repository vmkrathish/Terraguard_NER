import { Link } from "react-router-dom";
import { useDashboardData } from "../../hooks/useDashboardData";
import { DashboardError, DashboardLoading } from "../../components/DashboardStates";
import RiskBadge from "../../components/RiskBadge";
import StatusBadge from "../../components/StatusBadge";

// Field Officer view: ground-level, action-oriented. No model-metrics or
// system-health panels here — those belong on the Admin dashboard. This is
// "what do I need to do next", built entirely from real field_reports,
// risk_zones and alerts rows.
export default function FieldOfficerDashboardPage() {
  const { layers, alerts, reports, error, loading } = useDashboardData();

  if (error) return <DashboardError error={error} />;
  if (loading || !layers) return <DashboardLoading />;

  const pendingReports = reports.filter((r) => r.sync_status !== "synced");
  const myRecentReports = reports.slice(0, 6);
  const criticalZones = layers.risk_zones
    .filter((z) => z.risk_level === "CRITICAL" || z.risk_level === "HIGH")
    .slice(0, 6);
  const blockedRoads = layers.roads.filter((r) => r.status === "blocked");

  return (
    <div className="fade-in-up field-officer-dashboard">
      <div className="page-header">
        <div>
          <h2 className="page-title">Field Officer Dashboard</h2>
          <p className="page-subtitle">Ground-level view: report incidents, check active risk zones, and find safe routes.</p>
        </div>
      </div>

      <div className="grid grid-3">
        <Link to="/incidents" className="card stat-tile" style={{ textDecoration: "none", color: "inherit" }}>
          <span className="icon-chip">📝</span>
          <div className="value">Report</div>
          <div className="label">Submit a new field incident</div>
        </Link>
        <Link to="/route" className="card stat-tile" style={{ textDecoration: "none", color: "inherit" }}>
          <span className="icon-chip">🧭</span>
          <div className="value">Route</div>
          <div className="label">Find the safest way to a site</div>
        </Link>
        <div className="card stat-tile">
          <span className="icon-chip">⏳</span>
          <div className="value">{pendingReports.length}</div>
          <div className="label">Reports awaiting sync</div>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h3>Active high-risk zones nearby</h3>
          {criticalZones.length === 0 && <p className="table-empty">No HIGH/CRITICAL zones currently mapped.</p>}
          {criticalZones.length > 0 && (
            <table>
              <thead><tr><th>Zone</th><th>Level</th><th>Score</th></tr></thead>
              <tbody>
                {criticalZones.map((z) => (
                  <tr key={z.id}>
                    <td>{z.name}</td>
                    <td><RiskBadge level={z.risk_level} /></td>
                    <td>{z.risk_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {blockedRoads.length > 0 && (
            <p style={{ marginTop: 12, color: "var(--high)", fontWeight: 600, fontSize: 13 }}>
              ⚠ {blockedRoads.length} road segment(s) currently blocked — check the Emergency Route Optimizer before heading out.
            </p>
          )}
        </div>

        <div className="card">
          <h3>Your recent field reports</h3>
          {myRecentReports.length === 0 && <p className="table-empty">No field reports submitted yet.</p>}
          {myRecentReports.length > 0 && (
            <table>
              <thead><tr><th>Type</th><th>Severity</th><th>Status</th></tr></thead>
              <tbody>
                {myRecentReports.map((r) => (
                  <tr key={r.id}>
                    <td>{r.incident_type}</td>
                    <td><RiskBadge level={r.severity} /></td>
                    <td><StatusBadge status={r.sync_status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Recent alerts</h3>
        {alerts.length === 0 && <p className="table-empty">No alerts yet.</p>}
        {alerts.length > 0 && (
          <table>
            <thead><tr><th>Severity</th><th>Type</th><th>Reason</th></tr></thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td><RiskBadge level={a.severity} /></td>
                  <td>{a.alert_type}</td>
                  <td>{a.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
