import type { RouteOptimizeResponse } from "../../types";
import RiskBadge from "../RiskBadge";
import { riskLevelForScore } from "./routeMath";
import { RouteStatusLine, type RouteStatusKind } from "./RouteStatus";

interface RouteIntelligencePanelProps {
  result: RouteOptimizeResponse;
  status: RouteStatusKind;
  statusExplanation: string;
  usesBlockedRoad: boolean;
  emergencyLabel: string;
  strictAvoidance: boolean;
  nearRouteRiskZoneCount: number;
}

/** Route Intelligence panel (replaces the old plain "Result" card) — a
 * visual risk exposure bar, summary tiles, and a "Why this route?" list
 * built only from directly-evidenced real facts (spec section 18). */
export default function RouteIntelligencePanel({
  result, status, statusExplanation, usesBlockedRoad, emergencyLabel, strictAvoidance, nearRouteRiskZoneCount,
}: RouteIntelligencePanelProps) {
  const route = result.recommended_route;
  const riskLevel = riskLevelForScore(route.risk_score);
  const zone = result.destination_safe_zone;
  const usesLocalGraph = route.label.toLowerCase().includes("local_graph");

  const whyBullets: string[] = [];
  whyBullets.push(`Compatible with the ${emergencyLabel} emergency type you selected`);
  if (usesLocalGraph) whyBullets.push("Uses TerraGuard's local road graph, not a straight-line estimate");
  if (route.avoided_segments === 0) {
    whyBullets.push("No blocked roads were crossed");
  } else {
    whyBullets.push(`Route crosses ${route.avoided_segments} blocked road segment${route.avoided_segments === 1 ? "" : "s"} — no clear alternative existed`);
  }
  if (zone?.type === "hospital" && emergencyLabel.toLowerCase() === "medical") {
    whyBullets.push("Destination is a real hospital, matching the Medical emergency type");
  }
  if (zone) {
    whyBullets.push(
      zone.inside_risk_zone
        ? "Note: the nearest available option is still inside a mapped risk zone"
        : "Destination avoids mapped HIGH/CRITICAL risk areas"
    );
  }
  if (strictAvoidance) {
    whyBullets.push(
      nearRouteRiskZoneCount === 0
        ? "Client-side check found no mapped risk zones within their own radius along this route"
        : `Client-side check found ${nearRouteRiskZoneCount} mapped risk zone${nearRouteRiskZoneCount === 1 ? "" : "s"} within their own radius along this route`
    );
  }

  return (
    <div className="card route-intel-panel">
      <h3>Route Intelligence</h3>

      {route.network_coverage_warning && (
        <div className="form-alert error route-network-coverage-warning">
          <strong>Limited map coverage here.</strong> {route.network_coverage_warning}
        </div>
      )}

      <RouteStatusLine status={status} explanation={statusExplanation} />

      <div className="route-risk-exposure">
        <div className="route-risk-exposure-head">
          <span className="route-risk-exposure-label">Risk exposure</span>
          <RiskBadge level={riskLevel} />
        </div>
        <div className="route-risk-exposure-track">
          <div
            className="route-risk-exposure-fill"
            style={{ width: `${Math.max(2, Math.min(100, route.risk_score))}%`, background: `var(--${riskLevel.toLowerCase()})` }}
          />
        </div>
        <div className="route-risk-exposure-scale">
          <span>0</span><span>Risk score: {route.risk_score} / 100 (higher = more risk)</span><span>100</span>
        </div>
      </div>

      <div className="route-tiles">
        <div className="route-tile">
          <div className="route-tile-value">{route.distance_km} km</div>
          <div className="route-tile-label">Distance</div>
        </div>
        <div className="route-tile">
          <div className="route-tile-value">
            {route.estimated_time_minutes != null ? `${route.estimated_time_minutes} min` : "N/A"}
          </div>
          <div className="route-tile-label">ETA {route.estimated_time_minutes == null && "(not available)"}</div>
        </div>
        <div className={`route-tile ${route.avoided_segments > 0 ? "route-tile-warn" : ""}`}>
          <div className="route-tile-value">{route.avoided_segments}</div>
          <div className="route-tile-label">Blocked segments crossed</div>
        </div>
      </div>
      {route.estimated_time_minutes == null && (
        <p className="route-footnote">Not available from current data — TerraGuard's local road graph does not estimate travel time.</p>
      )}

      <h4 style={{ marginTop: 18 }}>Why this route?</h4>
      <ul className="route-why-list">
        {whyBullets.map((b, i) => <li key={i}>{b}</li>)}
      </ul>

      {usesBlockedRoad && (
        <div className="form-alert error" style={{ marginTop: 10 }}>
          ⚠ {route.label}
        </div>
      )}

      <p className="route-footnote" style={{ marginTop: 14 }}>{result.disclaimer}</p>
    </div>
  );
}
