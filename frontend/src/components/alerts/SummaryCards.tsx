import type { ThreatEntry } from "../../types";
import type { ThreatExtra } from "../../hooks/useAlertIntelligence";

interface Props {
  threats: ThreatEntry[];
  extras: Record<number, ThreatExtra>;
}

// Every figure here is derived live from real API data (GET /alerts/threats
// plus per-threat impact/lifecycle lookups) — never a fabricated number.
// Where the underlying data genuinely isn't available yet, the card says so
// honestly instead of showing a placeholder-looking value.
export default function SummaryCards({ threats, extras }: Props) {
  const activeThreats = threats.length;

  const awaitingAction = threats.filter((t) => {
    if (!t.latest_alert) return true;
    return t.latest_alert.status !== "resolved";
  }).length;

  const extraValues = threats.map((t) => extras[t.risk_zone_id]);
  const haveAnyExtras = extraValues.some((e) => e !== undefined);
  const knownPopValues = extraValues.filter((e) => e && e.populationKnown != null).map((e) => e!.populationKnown as number);
  const unknownPopCount = extraValues.filter((e) => e && e.populationKnown == null).length;
  const pendingExtrasCount = threats.length - extraValues.filter((e) => e !== undefined).length;
  const populationSum = knownPopValues.length > 0 ? knownPopValues.reduce((a, b) => a + b, 0) : null;

  const issuedThreats = threats.filter((t) => t.latest_alert);
  const assignedCount = issuedThreats.filter((t) => extras[t.risk_zone_id]?.assignedDone === true).length;
  const pendingResponseCount = issuedThreats.length - assignedCount;

  return (
    <div className="grid grid-4 summary-cards-grid">
      <div className="card stat-tile">
        <span className="icon-chip">⛰</span>
        <div className="value">{activeThreats > 0 ? activeThreats : "0"}</div>
        <div className="label">Active threats</div>
        {activeThreats === 0 && <div className="stat-sublabel">No active threats</div>}
      </div>

      <div className="card stat-tile">
        <span className="icon-chip">⏱</span>
        <div className="value">{awaitingAction}</div>
        <div className="label">Awaiting action</div>
        <div className="stat-sublabel">No warning issued yet, or response not yet resolved</div>
      </div>

      <div className="card stat-tile">
        <span className="icon-chip">👥</span>
        <div className="value">
          {!haveAnyExtras ? "Loading..." : populationSum == null ? "No verified data" : populationSum.toLocaleString()}
        </div>
        <div className="label">People in impact area</div>
        {haveAnyExtras && (unknownPopCount > 0 || pendingExtrasCount > 0) && (
          <div className="stat-sublabel">
            {unknownPopCount > 0 && `Population unknown for ${unknownPopCount} threat(s). `}
            {pendingExtrasCount > 0 && `Still loading ${pendingExtrasCount} threat(s).`}
          </div>
        )}
      </div>

      <div className="card stat-tile">
        <span className="icon-chip">📡</span>
        <div className="value">
          {issuedThreats.length === 0 ? "No warnings issued" : `${assignedCount} assigned / ${pendingResponseCount} pending`}
        </div>
        <div className="label">Response status</div>
      </div>
    </div>
  );
}
