export type RouteStatusKind = "idle" | "analyzing" | "found" | "caution" | "error";

const STATUS_META: Record<RouteStatusKind, { icon: string; label: string; className: string }> = {
  idle: { icon: "○", label: "IDLE", className: "route-status-idle" },
  analyzing: { icon: "◔", label: "ANALYZING", className: "route-status-analyzing" },
  found: { icon: "✓", label: "ROUTE FOUND", className: "route-status-found" },
  caution: { icon: "▲", label: "CAUTION", className: "route-status-caution" },
  error: { icon: "⛔", label: "ERROR", className: "route-status-error" },
};

/** Live status chip (spec section 12) — icon + label + color + one line of
 * real explanatory text, never color alone. `explanation` is built by the
 * caller from actual response fields (never a generic placeholder). */
export function RouteStatusChip({ status }: { status: RouteStatusKind }) {
  const meta = STATUS_META[status];
  return (
    <span className={`route-status-chip ${meta.className}`}>
      <span aria-hidden="true">{meta.icon}</span> {meta.label}
    </span>
  );
}

export function RouteStatusLine({ status, explanation }: { status: RouteStatusKind; explanation: string }) {
  const meta = STATUS_META[status];
  return (
    <div className={`route-status-line ${meta.className}`}>
      <span className="route-status-line-icon" aria-hidden="true">{meta.icon}</span>
      <div>
        <div className="route-status-line-label">{meta.label}</div>
        <div className="route-status-line-text">{explanation}</div>
      </div>
    </div>
  );
}
