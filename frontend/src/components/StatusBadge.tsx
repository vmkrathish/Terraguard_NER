// Generic status badge (sync/alert/workflow status — not risk severity) with
// the same icon+text+color pattern as RiskBadge. Maps only real status
// strings already returned by the API (FieldReport.sync_status,
// Alert.status) to a semantic tone; anything unrecognized falls back to a
// neutral badge showing the raw value rather than guessing.
const TONE_MAP: Record<string, "GOOD" | "WARN" | "BAD" | "NEUTRAL"> = {
  synced: "GOOD",
  active: "WARN",
  resolved: "GOOD",
  pending: "WARN",
  pending_sync: "WARN",
  failed: "BAD",
  dismissed: "NEUTRAL",
};

const ICON_MAP: Record<"GOOD" | "WARN" | "BAD" | "NEUTRAL", string> = {
  GOOD: "✓",
  WARN: "●",
  BAD: "✕",
  NEUTRAL: "•",
};

export default function StatusBadge({ status }: { status: string }) {
  const tone = TONE_MAP[status] ?? "NEUTRAL";
  return (
    <span className={`badge badge-${tone}`}>
      <span className="badge-icon" aria-hidden="true">{ICON_MAP[tone]}</span>
      {status}
    </span>
  );
}
