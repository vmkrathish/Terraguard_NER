// Risk-severity badge: icon + text + color together, so the signal never
// depends on color alone (accessibility for colorblind users and print).
// Accepts the risk_zones vocabulary (LOW/MODERATE/HIGH/CRITICAL) in any
// case, since some real API fields (e.g. field_reports.severity,
// alerts.severity) come back lowercase.
const ICONS: Record<string, string> = {
  LOW: "●",
  MODERATE: "▲",
  HIGH: "▲",
  CRITICAL: "⛔",
};

export default function RiskBadge({ level }: { level: string }) {
  const normalized = (level || "").toUpperCase();
  const known = normalized in ICONS;
  const cls = known ? normalized : "NEUTRAL";
  return (
    <span className={`badge badge-${cls}`}>
      <span className="badge-icon" aria-hidden="true">{ICONS[normalized] ?? "•"}</span>
      {level}
    </span>
  );
}
