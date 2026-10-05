import type { ThreatEntry } from "../../types";
import ThreatCard from "./ThreatCard";

interface Props {
  threats: ThreatEntry[];
  loading: boolean;
  onSimulate: (t: ThreatEntry) => void;
  onIssueWarning: (t: ThreatEntry) => void;
  onOpenWarRoom: (alertId: number) => void;
}

export default function ThreatBoard({ threats, loading, onSimulate, onIssueWarning, onOpenWarRoom }: Props) {
  return (
    <div className="card">
      <h3>Live threat board</h3>
      <p className="page-subtitle" style={{ marginBottom: "var(--sp-4)" }}>
        Every high/critical risk zone, surfaced automatically from live risk-zone data — whether or not a warning has
        been issued for it yet.
      </p>
      {loading && threats.length === 0 && <p className="table-empty">Loading threat board...</p>}
      {!loading && threats.length === 0 && <p className="table-empty">No active threats — no risk zone is currently at HIGH or CRITICAL level.</p>}
      <div className="threat-board-grid">
        {threats.map((t) => (
          <ThreatCard
            key={t.risk_zone_id}
            threat={t}
            onSimulate={onSimulate}
            onIssueWarning={onIssueWarning}
            onOpenWarRoom={onOpenWarRoom}
          />
        ))}
      </div>
    </div>
  );
}
