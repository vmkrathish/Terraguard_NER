import type { Evidence } from "../../types";

// The 5-signal evidence chain — always rendered as verified/pending with its
// real `detail` text, NEVER as a percentage/confidence score. Severity
// (risk_level) is shown elsewhere and must never be blended with this count.
export default function EvidenceChain({ evidence, compact = false }: { evidence: Evidence; compact?: boolean }) {
  return (
    <div className="evidence-chain">
      <div className="evidence-chain-header">
        <span className="section-label" style={{ margin: 0 }}>Evidence chain</span>
        <span className="evidence-chain-count">{evidence.verified_count}/{evidence.total_count} signals available</span>
      </div>
      <ul className="evidence-chain-list">
        {evidence.signals.map((s) => (
          <li key={s.key} className={`evidence-signal ${s.verified ? "verified" : "pending"}`}>
            <span className="evidence-signal-icon" aria-hidden="true">{s.verified ? "✓" : "○"}</span>
            <div className="evidence-signal-body">
              <span className="evidence-signal-label">{s.label}</span>
              {!compact && <span className="evidence-signal-detail">{s.detail}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
