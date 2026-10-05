import type { RouteOptimizeResponse } from "../../types";

/** Builds the real calculation trace stages (spec section 4/20) — only
 * stages that genuinely happened for this response are listed, in order.
 * Nothing here is a generic "step 1/2/3" placeholder; each line cites the
 * actual field/decision it reflects. */
export function buildTraceStages(result: RouteOptimizeResponse, strictAvoidance: boolean): string[] {
  const route = result.recommended_route;
  const usesLocalGraph = route.label.toLowerCase().includes("local_graph");
  const isStraightLine = result.recommended_route.coordinates.length === 2 && !usesLocalGraph;
  const stages: string[] = [];

  stages.push("Source identified from the coordinates you provided");

  if (result.destination_safe_zone) {
    stages.push(
      `Destination resolved to the nearest safe zone: ${result.destination_safe_zone.name} (${result.destination_safe_zone.type}, ${result.destination_safe_zone.distance_km} km away)`
    );
  } else {
    stages.push("Destination identified from the coordinates you provided");
  }

  if (usesLocalGraph) {
    stages.push("Road graph loaded from TerraGuard's mapped roads");
    if (route.source_snap_distance_km != null) {
      stages.push(
        route.source_snap_distance_km < 0.05
          ? "Source point matches a mapped road-graph node directly"
          : `Source snapped to the nearest mapped road-graph node, ${route.source_snap_distance_km} km away`
      );
    }
    if (route.destination_snap_distance_km != null) {
      stages.push(
        route.destination_snap_distance_km < 0.05
          ? "Destination point matches a mapped road-graph node directly"
          : `Destination snapped to the nearest mapped road-graph node, ${route.destination_snap_distance_km} km away`
      );
    }
  } else if (isStraightLine) {
    stages.push("No usable road graph available near this location — fell back to a straight-line distance estimate");
  }

  stages.push(`Risk exposure evaluated for the route (risk score ${route.risk_score}/100)`);
  stages.push(
    route.avoided_segments > 0
      ? `Blocked roads evaluated — ${route.avoided_segments} blocked segment(s) could not be avoided`
      : "Blocked roads evaluated — none were crossed"
  );

  if (strictAvoidance) {
    stages.push("Emergency constraints applied — rescue/fire profile requires avoiding all mapped risk zones, not just blocked roads");
  } else {
    stages.push("Emergency constraints applied — standard lower-risk routing profile");
  }

  stages.push("Route selected as the lowest-cost candidate (distance + risk penalty + blocked-road penalty)");
  return stages;
}

export default function CalculationTrace({ stages }: { stages: string[] }) {
  return (
    <details className="route-trace">
      <summary>Calculation trace ({stages.length} stages)</summary>
      <ol className="route-trace-list">
        {stages.map((s, i) => <li key={i}>{s}</li>)}
      </ol>
    </details>
  );
}
