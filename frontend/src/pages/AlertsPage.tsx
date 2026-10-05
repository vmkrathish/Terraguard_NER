import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useAlertIntelligence } from "../hooks/useAlertIntelligence";
import type { Alert, ThreatEntry } from "../types";
import RiskBadge from "../components/RiskBadge";
import StatusBadge from "../components/StatusBadge";
import SummaryCards from "../components/alerts/SummaryCards";
import ThreatBoard from "../components/alerts/ThreatBoard";
import RoleFocusPanel from "../components/alerts/RoleFocusPanel";
import ImpactSimulatorModal from "../components/alerts/ImpactSimulatorModal";
import AlertComposer from "../components/alerts/AlertComposer";
import WarRoom from "../components/alerts/WarRoom";
import TestAlertPanel from "../components/alerts/TestAlertPanel";

interface SimulatorState {
  title: string;
  lat: number;
  lon: number;
  radiusM: number;
}

export default function AlertsPage() {
  const { user } = useAuth();
  const { threats, alerts, extras, loading, error, lastUpdated, reload } = useAlertIntelligence();

  const [warRoomAlertId, setWarRoomAlertId] = useState<number | null>(null);
  const [simulator, setSimulator] = useState<SimulatorState | null>(null);
  const [composerThreat, setComposerThreat] = useState<ThreatEntry | "manual" | null>(null);

  const openSimulatorForThreat = (t: ThreatEntry) =>
    // The threat board doesn't expose each risk zone's own radius_m, only its
    // evidence/impact computed at that radius server-side — so the simulator
    // uses the same documented 20000m default the rest of the ad-hoc
    // evidence/impact endpoints use, rather than guessing at the zone's own value.
    setSimulator({ title: t.name, lat: t.latitude, lon: t.longitude, radiusM: 20000 });

  const onIssued = (alert: Alert) => {
    setComposerThreat(null);
    reload();
    setWarRoomAlertId(alert.id);
  };

  const roleSubtitle =
    user?.role === "field_officer"
      ? "Your assigned-area view: safe routes, field confirmation status and issued warnings near you."
      : user?.role === "admin"
      ? "System pipeline and audit-trail view: detection through resolution across every threat and alert."
      : "Command-center view: threat evidence, impact, response assignment and acknowledgement tracking.";

  return (
    <div className="alerts-page">
      <div className="page-header">
        <div>
          <h2 className="page-title">
            Alert Intelligence Center
            <span className="live-dot" aria-hidden="true" /> <span className="live-label">LIVE SYSTEM</span>
          </h2>
          <p className="page-subtitle">{roleSubtitle}</p>
          <p className="page-subtitle" style={{ margin: 0, fontSize: "var(--fs-xs)" }}>
            Last updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : "loading..."}
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setComposerThreat("manual")}>+ New Warning</button>
      </div>

      {error && <div className="form-alert error">Could not reach the backend API: {error}</div>}

      <SummaryCards threats={threats} extras={extras} />

      {warRoomAlertId != null ? (
        <WarRoom
          alertId={warRoomAlertId}
          currentUserRole={user?.role}
          onClose={() => setWarRoomAlertId(null)}
          onOpenSimulator={(title, lat, lon, radiusM) => setSimulator({ title, lat, lon, radiusM })}
        />
      ) : (
        <>
          <RoleFocusPanel role={user?.role} threats={threats} extras={extras} />

          <ThreatBoard
            threats={threats}
            loading={loading}
            onSimulate={openSimulatorForThreat}
            onIssueWarning={(t) => setComposerThreat(t)}
            onOpenWarRoom={setWarRoomAlertId}
          />

          <div className="card">
            <h3>Issued alert history ({alerts.length})</h3>
            {alerts.length === 0 && <p className="table-empty">No alerts recorded yet.</p>}
            {alerts.length > 0 && (
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Severity</th><th>Type</th><th>Reason</th><th>Status</th><th></th></tr></thead>
                  <tbody>
                    {alerts.map((a) => (
                      <tr key={a.id}>
                        <td><RiskBadge level={a.severity} /></td>
                        <td>{a.alert_type}</td>
                        <td>{a.reason}</td>
                        <td><StatusBadge status={a.status} /></td>
                        <td><button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => setWarRoomAlertId(a.id)} disabled={a.latitude == null || a.longitude == null}>Open War Room</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <TestAlertPanel onSent={reload} />
        </>
      )}

      {simulator && (
        <ImpactSimulatorModal
          title={simulator.title}
          lat={simulator.lat}
          lon={simulator.lon}
          radiusM={simulator.radiusM}
          onClose={() => setSimulator(null)}
        />
      )}

      {composerThreat && (
        <AlertComposer
          prefillThreat={composerThreat === "manual" ? null : composerThreat}
          onClose={() => setComposerThreat(null)}
          onIssued={onIssued}
        />
      )}
    </div>
  );
}
