import type { RouteOut } from "../../types";
import { BLOCKED_PENALTY_KM, RISK_PENALTY_PER_POINT_KM } from "./routeMath";

interface Bar {
  label: string;
  valueKm: number;
  note: string;
  className: string;
}

function buildBars(route: RouteOut): Bar[] {
  const riskPenaltyKm = Math.round(route.risk_score * RISK_PENALTY_PER_POINT_KM * 100) / 100;
  const blockedPenaltyKm = route.avoided_segments > 0 ? Math.round(route.avoided_segments * BLOCKED_PENALTY_KM * 100) / 100 : 0;
  return [
    { label: "Distance", valueKm: route.distance_km, note: `${route.distance_km} km (real, from the computed route)`, className: "bar-distance" },
    { label: "Risk penalty", valueKm: riskPenaltyKm, note: `${route.risk_score} risk score × ${RISK_PENALTY_PER_POINT_KM} km/point = ${riskPenaltyKm} km-equivalent`, className: "bar-risk" },
    {
      label: "Blocked-road impact",
      valueKm: blockedPenaltyKm,
      note: route.avoided_segments > 0
        ? `${route.avoided_segments} blocked segment(s) crossed × ${BLOCKED_PENALTY_KM} km penalty = ${blockedPenaltyKm} km-equivalent`
        : "0 — no blocked segments crossed",
      className: "bar-blocked",
    },
  ];
}

/** Route Decision Breakdown (spec section 8) — shows only real cost
 * components from `route_optimizer.py`'s actual sort key:
 * `distance_km + risk_score * RISK_PENALTY_PER_POINT_KM` (0.15), plus the
 * real `BLOCKED_PENALTY_KM` (50.0) baked into the road graph's edge weights.
 * There is deliberately no 4th "accessibility" bar — the backend does not
 * implement one. */
export default function RouteDecisionBreakdown({ recommended, alternative }: { recommended: RouteOut; alternative: RouteOut | null }) {
  const bars = buildBars(recommended);
  const maxVal = Math.max(1, ...bars.map((b) => b.valueKm));

  return (
    <div className="card">
      <h3>Route decision breakdown</h3>
      <p className="page-subtitle" style={{ marginBottom: 14 }}>
        The distance, risk, and blocked-road cost components used for this route.
      </p>
      <div className="route-breakdown-bars">
        {bars.map((b) => (
          <div key={b.label} className="route-breakdown-bar">
            <div className="route-breakdown-bar-head">
              <span>{b.label}</span>
              <span className="route-breakdown-bar-value">{b.valueKm} km-eq.</span>
            </div>
            <div className="route-breakdown-track">
              <div className={`route-breakdown-fill ${b.className}`} style={{ width: `${Math.max(b.valueKm > 0 ? 2 : 0, (b.valueKm / maxVal) * 100)}%` }} />
            </div>
            <div className="route-footnote">{b.note}</div>
          </div>
        ))}
      </div>

      {/* Comparison path kept for when the backend ever returns a second
          candidate route — alternative_route is realistically always null
          today, since optimize_route() only ever builds one candidate. */}
      {alternative && (
        <div className="route-alt-comparison">
          <h4>Alternative route (comparison)</h4>
          <table>
            <thead><tr><th></th><th>Recommended</th><th>Alternative</th></tr></thead>
            <tbody>
              <tr><td>Distance</td><td>{recommended.distance_km} km</td><td>{alternative.distance_km} km</td></tr>
              <tr><td>Risk score</td><td>{recommended.risk_score}</td><td>{alternative.risk_score}</td></tr>
              <tr><td>Blocked segments crossed</td><td>{recommended.avoided_segments}</td><td>{alternative.avoided_segments}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      <p className="route-footnote" style={{ marginTop: 12 }}>
        TerraGuard's current routing model does not score accessibility separately.
      </p>
    </div>
  );
}
