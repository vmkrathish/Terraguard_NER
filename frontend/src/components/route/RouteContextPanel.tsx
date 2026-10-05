import RiskBadge from "../RiskBadge";
import { EVENT_CONTEXT_RADIUS_KM, type NearbyEventHit, type NearbyRiskZoneHit } from "./routeMath";

interface RouteContextPanelProps {
  riskZoneHits: NearbyRiskZoneHit[];
  eventHits: NearbyEventHit[];
  blockedRoadHits: { id: number; name: string; road_type: string; blocked_reason: string | null; distance_to_route_km: number }[];
}

/** Route context (spec section 14 + blocked-road detail from section 9) —
 * real risk_zones/landslide_events/roads from GET /map/layers, filtered to
 * those geometrically near the computed route. Counts are always shown,
 * including zero, never hidden. */
export default function RouteContextPanel({ riskZoneHits, eventHits, blockedRoadHits }: RouteContextPanelProps) {
  return (
    <div className="card">
      <h3>Route context</h3>

      <h4>Blocked roads near this route</h4>
      {blockedRoadHits.length === 0 ? (
        <p className="route-footnote">No mapped blocked roads within {EVENT_CONTEXT_RADIUS_KM} km of this route.</p>
      ) : (
        <ul className="route-context-list">
          {blockedRoadHits.map((r) => (
            <li key={r.id}>
              <b>{r.name}</b> ({r.road_type}) — {r.distance_to_route_km} km from route
              <div className="route-footnote">Reason: {r.blocked_reason || "No reason recorded"}</div>
            </li>
          ))}
        </ul>
      )}

      <h4>Known hazards near this route</h4>
      <p className="route-footnote" style={{ marginTop: -6 }}>
        {riskZoneHits.length} mapped risk zone{riskZoneHits.length === 1 ? "" : "s"} intersect this route's path (route passes within
        that zone's own mapped radius) · {eventHits.length} historical landslide event{eventHits.length === 1 ? "" : "s"} within{" "}
        {EVENT_CONTEXT_RADIUS_KM} km (a display radius chosen for this page, not a backend value).
      </p>

      {riskZoneHits.length > 0 && (
        <ul className="route-context-list">
          {riskZoneHits.map((z) => (
            <li key={z.id}>
              <b>{z.name}</b> <RiskBadge level={z.risk_level} /> — route passes within {Math.round(z.radius_m)} m of its center
            </li>
          ))}
        </ul>
      )}

      {eventHits.length > 0 && (
        <ul className="route-context-list">
          {eventHits.map((e) => (
            <li key={e.id}>
              <b>{e.event_title || `${e.district}, ${e.state}`}</b> ({e.severity || "unknown"}) — {e.distance_to_route_km} km from route
              {e.event_date && <span className="route-footnote"> · {e.event_date}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
