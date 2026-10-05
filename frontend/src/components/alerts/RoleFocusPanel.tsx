import type { ThreatEntry } from "../../types";
import type { ThreatExtra } from "../../hooks/useAlertIntelligence";
import StatusBadge from "../StatusBadge";

interface Props {
  role: string | undefined;
  threats: ThreatEntry[];
  extras: Record<number, ThreatExtra>;
}

// Same shared components/data for every role (per the existing dashboard
// pattern) — only which content is emphasized changes, based on the
// signed-in user's real role from AuthContext.
export default function RoleFocusPanel({ role, threats, extras }: Props) {
  if (role === "field_officer") {
    return (
      <div className="card">
        <h3>Field officer focus — safe routes &amp; field confirmation</h3>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Threat</th><th>District</th><th>Safe route</th><th>Blocked roads</th><th>Field confirmation</th></tr></thead>
            <tbody>
              {threats.map((t) => {
                const extra = extras[t.risk_zone_id];
                const fieldSignal = t.evidence.signals.find((s) => s.key === "field_confirmation");
                return (
                  <tr key={t.risk_zone_id}>
                    <td>{t.name}</td>
                    <td>{t.district}</td>
                    <td>{extra?.safeZoneDistanceKm != null ? `${extra.safeZoneDistanceKm.toFixed(1)} km` : "Unavailable"}</td>
                    <td>{extra ? extra.blockedRoadsCount : "..."}</td>
                    <td>{fieldSignal ? (fieldSignal.verified ? "✓ Confirmed" : "○ Not yet confirmed") : "n/a"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (role === "admin") {
    const notYetIssued = threats.filter((t) => !t.latest_alert).length;
    const issuedActive = threats.filter((t) => t.latest_alert && t.latest_alert.status !== "resolved").length;
    const resolved = threats.filter((t) => t.latest_alert && t.latest_alert.status === "resolved").length;
    return (
      <div className="card">
        <h3>Admin focus — pipeline &amp; audit trail</h3>
        <p className="page-subtitle" style={{ marginBottom: 8 }}>
          Every stage change, assignment and acknowledgement below is written to the real lifecycle/acknowledgement
          tables and is visible per-alert in that alert's War Room timeline — nothing here is a separate audit log.
        </p>
        <div className="grid grid-3">
          <div className="impact-stat"><div className="impact-stat-value">{notYetIssued}</div><div className="impact-stat-label">Detected, not yet issued</div></div>
          <div className="impact-stat"><div className="impact-stat-value">{issuedActive}</div><div className="impact-stat-label">Issued, active response</div></div>
          <div className="impact-stat"><div className="impact-stat-value">{resolved}</div><div className="impact-stat-label">Resolved</div></div>
        </div>
      </div>
    );
  }

  // authority (default): severity / evidence / impact / route / teams / acknowledgement / escalation emphasis.
  return (
    <div className="card">
      <h3>Authority focus — severity, evidence &amp; response oversight</h3>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Threat</th><th>Severity</th><th>Evidence</th><th>Impact</th><th>Response</th></tr></thead>
          <tbody>
            {threats.map((t) => (
              <tr key={t.risk_zone_id}>
                <td>{t.name}</td>
                <td>{t.risk_level}</td>
                <td>{t.evidence.verified_count}/{t.evidence.total_count} signals</td>
                <td>{t.impact_summary.village_count}v / {t.impact_summary.road_count}r / {t.impact_summary.facility_count}f</td>
                <td><StatusBadge status={t.latest_alert ? t.latest_alert.status : "pending"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
