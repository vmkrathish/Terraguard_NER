import { useState } from "react";
import { api } from "../../api/client";
import type { AckRole, AcknowledgementMap } from "../../types";

const ROLE_ORDER: { role: AckRole; label: string }[] = [
  { role: "field_officer", label: "Field Officer" },
  { role: "authority", label: "Authority" },
  { role: "admin", label: "Admin" },
  { role: "community", label: "Community" },
  { role: "emergency_team", label: "Emergency Team" },
];

interface Props {
  alertId: number;
  acknowledgements: AcknowledgementMap;
  currentUserRole: string | undefined;
  onChanged: () => void;
}

// Per-role acknowledgement status. Community/Emergency Team are always
// rendered with a visible SIMULATION badge (backend channel_type ===
// "simulation") — there is no real notification delivery or account system
// behind them, and they must never look like a real delivered notification.
export default function AcknowledgementPanel({ alertId, acknowledgements, currentUserRole, onChanged }: Props) {
  const [busyRole, setBusyRole] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const acknowledge = async (role: AckRole, isSimulation: boolean) => {
    setBusyRole(role);
    setError(null);
    try {
      await api.post(`/alerts/${alertId}/acknowledge`, isSimulation ? { role } : {});
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to acknowledge as ${role}`);
    } finally {
      setBusyRole(null);
    }
  };

  return (
    <div className="ack-grid">
      {ROLE_ORDER.map(({ role, label }) => {
        const status = acknowledgements[role];
        const isSimulation = status.channel_type === "simulation";
        const canAckAsRealRole = !isSimulation && currentUserRole === role;
        return (
          <div key={role} className="ack-item">
            <div className="ack-item-head">
              <strong>{label}</strong>
              {isSimulation && <span className="sim-badge">SIMULATION</span>}
            </div>
            {status.acknowledged ? (
              <div className="ack-item-status good">
                <span aria-hidden="true">✓</span> Acknowledged
                {status.acknowledged_by && ` by ${status.acknowledged_by}`}
                {status.acknowledged_at && ` — ${new Date(status.acknowledged_at).toLocaleString()}`}
              </div>
            ) : (
              <div className="ack-item-status pending">
                <span aria-hidden="true">○</span> Not yet acknowledged
                {!isSimulation && !canAckAsRealRole && (
                  <div className="impact-stat-note">Only a signed-in {label} account can acknowledge for real.</div>
                )}
              </div>
            )}
            {!status.acknowledged && (isSimulation || canAckAsRealRole) && (
              <button
                className="btn btn-ghost"
                style={{ marginTop: 6, fontSize: 12 }}
                disabled={busyRole === role}
                onClick={() => acknowledge(role, isSimulation)}
              >
                {busyRole === role ? "Recording..." : isSimulation ? "Simulate acknowledgement" : `Acknowledge as ${label}`}
              </button>
            )}
          </div>
        );
      })}
      {error && <div className="form-alert error">{error}</div>}
    </div>
  );
}
