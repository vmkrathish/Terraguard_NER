import { useState } from "react";
import type { MapLayers, RouteOptimizeResponse } from "../../types";
import { nearestByDistance, sampleRoutePoints } from "./routeMath";

interface RouteExplorerProps {
  result: RouteOptimizeResponse;
  layers: MapLayers | null;
}

/** Route Explorer (spec section 16) — a client-side view over the already-
 * fetched `recommended_route.coordinates`, showing the nearest real risk
 * zone and nearest real facility (hospital/school/village) to a handful of
 * sampled points along the route. Nothing here is a new API call or an
 * invented value; every distance is computed from the same GET
 * /map/layers rows the map itself renders. */
export default function RouteExplorer({ result, layers }: RouteExplorerProps) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const samples = sampleRoutePoints(result.recommended_route.coordinates);

  const facilities = layers
    ? [
        ...layers.hospitals.map((h) => ({ ...h, kind: "hospital" as const })),
        ...layers.schools.map((s) => ({ ...s, kind: "school" as const })),
        ...layers.villages.map((v) => ({ ...v, kind: "village" as const })),
      ]
    : [];

  return (
    <div className="card">
      <h3>Route explorer</h3>
      <p className="page-subtitle" style={{ marginBottom: 12 }}>
        {samples.length} sampled points along the computed route (evenly spaced by position in the route, a display choice — not a
        backend concept), each showing the nearest real risk zone and facility from TerraGuard's mapped data.
      </p>
      <ul className="route-explorer-list">
        {samples.map((pt, i) => {
          const nearestZone = layers ? nearestByDistance(pt, layers.risk_zones) : null;
          const nearestFacility = nearestByDistance(pt, facilities);
          const open = openIndex === i;
          return (
            <li key={i} className="route-explorer-item">
              <button type="button" className="route-explorer-toggle" onClick={() => setOpenIndex(open ? null : i)}>
                Point {i + 1} of {samples.length} <span className="route-footnote">({pt.lat.toFixed(4)}, {pt.lon.toFixed(4)})</span>
                <span className="route-control-edit">{open ? "Hide" : "Details"}</span>
              </button>
              {open && (
                <div className="route-explorer-detail">
                  <div>
                    Nearest risk zone: {nearestZone
                      ? `${nearestZone.item.name} (${nearestZone.item.risk_level}, ${nearestZone.distance_km} km away)`
                      : "No mapped risk zones"}
                  </div>
                  <div>
                    Nearest facility: {nearestFacility
                      ? `${nearestFacility.item.name} (${(nearestFacility.item as any).kind}, ${nearestFacility.distance_km} km away)`
                      : "No mapped facilities"}
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
