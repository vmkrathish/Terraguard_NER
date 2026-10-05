import type { ThreatEntry } from "../../types";
import RiskBadge from "../RiskBadge";
import StatusBadge from "../StatusBadge";
import EvidenceChain from "./EvidenceChain";

interface Props {
  threat: ThreatEntry;
  onSimulate: (t: ThreatEntry) => void;
  onIssueWarning: (t: ThreatEntry) => void;
  onOpenWarRoom: (alertId: number) => void;
}

export default function ThreatCard({ threat, onSimulate, onIssueWarning, onOpenWarRoom }: Props) {
  const responseLabel = threat.latest_alert
    ? threat.latest_alert.status === "resolved"
      ? "Resolved"
      : "Warning issued — response in progress"
    : "Not yet issued";

  return (
    <div className="card threat-card">
      <div className="threat-card-head">
        <div>
          <RiskBadge level={threat.risk_level} />
          <h3 style={{ margin: "6px 0 2px" }}>{threat.name}</h3>
          <div className="threat-card-loc">{threat.district}, {threat.state}</div>
        </div>
        <div className="threat-card-response">
          <StatusBadge status={threat.latest_alert ? threat.latest_alert.status : "pending"} />
          <div className="threat-card-response-label">{responseLabel}</div>
        </div>
      </div>

      <EvidenceChain evidence={threat.evidence} compact />

      <div className="threat-card-impact">
        <span>{threat.impact_summary.village_count} village(s)</span>
        <span>{threat.impact_summary.road_count} road(s)</span>
        <span>{threat.impact_summary.facility_count} facility(ies)</span>
      </div>

      <div className="threat-card-actions">
        <button className="btn btn-ghost" onClick={() => onSimulate(threat)}>Simulate Impact</button>
        {threat.latest_alert ? (
          <button className="btn btn-ghost" onClick={() => onOpenWarRoom(threat.latest_alert!.id)}>Open War Room</button>
        ) : (
          <button className="btn btn-primary" onClick={() => onIssueWarning(threat)}>Issue Warning</button>
        )}
      </div>
    </div>
  );
}
