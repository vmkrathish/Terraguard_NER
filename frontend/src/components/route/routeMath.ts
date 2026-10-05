/* ==========================================================================
   Route math helpers — Emergency Route Center.

   Every threshold/formula below is copied from a real backend source file,
   cited inline. Nothing here invents a new bucket boundary or cost term.
   The two "UI-chosen" constants (context radius, sample count) are called
   out explicitly as display choices, not backend values.
   ========================================================================== */

/** Great-circle distance in km — same haversine formula as
 * `backend/app/services/geo_utils.py::haversine_km` (ported, not copy-pasted,
 * since the backend uses Python/pandas and this runs client-side on plain
 * arrays of [lon, lat] pairs). */
export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371.0; // km, same EARTH_RADIUS_M/1000 as geo_utils.py
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLambda = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLambda / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/** Shortest distance (km) from a point to a polyline of [lon, lat] vertices.
 * Client-side port of the *concept* in `geo_utils.py::point_to_linestring_distance_m`
 * (project to a local equirectangular metre grid, then planar point-to-segment
 * distance) — simplified to plain trig since this only drives UI display
 * (nearby hazard counts), not the routing decision itself. */
export function pointToRouteDistanceKm(lat: number, lon: number, coords: [number, number][]): number {
  if (coords.length === 0) return Infinity;
  if (coords.length === 1) return haversineKm(lat, lon, coords[0][1], coords[0][0]);

  // Local equirectangular projection centered on the point's own latitude —
  // accurate enough for the short (<1-2 degree) spans every TerraGuard NER
  // road/route spans, same reasoning geo_utils.py documents for its own
  // local projection.
  const centerLat = lat;
  const mPerDegLat = 111132.92 - 559.82 * Math.cos((2 * centerLat * Math.PI) / 180);
  const mPerDegLon = (Math.PI / 180) * 6371000 * Math.cos((centerLat * Math.PI) / 180);
  const project = (lonV: number, latV: number): [number, number] => [lonV * mPerDegLon, latV * mPerDegLat];

  const [px, py] = project(lon, lat);
  let best = Infinity;
  for (let i = 0; i < coords.length - 1; i++) {
    const [ax, ay] = project(coords[i][0], coords[i][1]);
    const [bx, by] = project(coords[i + 1][0], coords[i + 1][1]);
    const dx = bx - ax;
    const dy = by - ay;
    const lenSq = dx * dx + dy * dy;
    let t = lenSq === 0 ? 0 : ((px - ax) * dx + (py - ay) * dy) / lenSq;
    t = Math.max(0, Math.min(1, t));
    const cx = ax + t * dx;
    const cy = ay + t * dy;
    const d = Math.sqrt((px - cx) ** 2 + (py - cy) ** 2) / 1000; // metres -> km
    if (d < best) best = d;
  }
  return best;
}

/** Risk severity bucket for a 0-100 risk_score. Thresholds copied verbatim
 * from `backend/app/core/config.py`: RISK_LOW_MAX=24, RISK_MODERATE_MAX=49,
 * RISK_HIGH_MAX=74 (so LOW <= 24, MODERATE 25-49, HIGH 50-74, CRITICAL > 74).
 * This is the single source of truth for the route page's risk-level
 * labeling — never redefine these numbers elsewhere. */
export function riskLevelForScore(score: number): "LOW" | "MODERATE" | "HIGH" | "CRITICAL" {
  if (score <= 24) return "LOW";
  if (score <= 49) return "MODERATE";
  if (score <= 74) return "HIGH";
  return "CRITICAL";
}

// Real backend constants (route_optimizer.py) — cited, not guessed.
export const RISK_PENALTY_PER_POINT_KM = 0.15; // route_optimizer.py RISK_PENALTY_PER_POINT_KM
export const BLOCKED_PENALTY_KM = 50.0; // route_optimizer.py BLOCKED_PENALTY_KM
export const NETWORK_SNAP_WARNING_KM = 5.0; // route_optimizer.py NETWORK_SNAP_WARNING_KM

// UI-chosen display constants (NOT backend values) — documented here and in
// EMERGENCY_ROUTE_CENTER_NOTES.md so nobody mistakes them for API data.
/** How close (km) a historical landslide event must be to a route's polyline
 * to be listed as "near this route" in the Route Context card. Our own
 * display choice — the backend does not define a route-proximity radius. */
export const EVENT_CONTEXT_RADIUS_KM = 10;
/** Number of evenly-spaced points sampled along the route polyline for the
 * Route Explorer / Replay views. A display choice, not a backend concept. */
export const ROUTE_EXPLORER_SAMPLE_COUNT = 6;

export interface NearbyRiskZoneHit {
  id: number;
  name: string;
  risk_level: string;
  risk_score: number;
  radius_m: number;
  distance_to_route_km: number;
}

/** Real risk_zones (from GET /map/layers) whose own real radius_m actually
 * reaches the route polyline — i.e. the route passes within that zone's own
 * mapped radius, not an arbitrary UI radius. Mirrors the "does the route
 * path pass within radius_m" check `route_optimizer.py::_risk_zone_hits`
 * uses server-side for the rescue/fire strict-avoidance profile, ported to
 * run client-side over the already-fetched map layers for display. */
export function findRiskZonesNearRoute(
  coords: [number, number][],
  riskZones: { id: number; name: string; latitude: number; longitude: number; radius_m: number; risk_score: number; risk_level: string }[]
): NearbyRiskZoneHit[] {
  const hits: NearbyRiskZoneHit[] = [];
  for (const z of riskZones) {
    const distKm = pointToRouteDistanceKm(z.latitude, z.longitude, coords);
    if (distKm * 1000 <= z.radius_m) {
      hits.push({ id: z.id, name: z.name, risk_level: z.risk_level, risk_score: z.risk_score, radius_m: z.radius_m, distance_to_route_km: Math.round(distKm * 1000) / 1000 });
    }
  }
  return hits.sort((a, b) => a.distance_to_route_km - b.distance_to_route_km);
}

export interface NearbyEventHit {
  id: number;
  event_title: string | null;
  district: string;
  state: string;
  severity: string;
  event_date: string | null;
  distance_to_route_km: number;
}

/** Real landslide_events within EVENT_CONTEXT_RADIUS_KM (our own display
 * radius, documented above — not a backend concept) of the route polyline. */
export function findEventsNearRoute(
  coords: [number, number][],
  events: { id: number; latitude: number; longitude: number; event_title: string | null; district: string; state: string; severity: string; event_date: string | null }[],
  radiusKm: number = EVENT_CONTEXT_RADIUS_KM
): NearbyEventHit[] {
  const hits: NearbyEventHit[] = [];
  for (const e of events) {
    const distKm = pointToRouteDistanceKm(e.latitude, e.longitude, coords);
    if (distKm <= radiusKm) {
      hits.push({ id: e.id, event_title: e.event_title, district: e.district, state: e.state, severity: e.severity, event_date: e.event_date, distance_to_route_km: Math.round(distKm * 10) / 10 });
    }
  }
  return hits.sort((a, b) => a.distance_to_route_km - b.distance_to_route_km);
}

/** Real roads (status === "blocked") whose parsed geojson line lies within
 * `radiusKm` of the route polyline — used for "blocked roads near this
 * route" context, distinct from `avoided_segments` (which only counts
 * blocked edges the route was actually forced to cross). */
export function findBlockedRoadsNearRoute(
  coords: [number, number][],
  roads: { id: number; name: string; road_type: string; status: string; blocked_reason: string | null; geojson: string }[],
  radiusKm: number = EVENT_CONTEXT_RADIUS_KM
): { id: number; name: string; road_type: string; blocked_reason: string | null; distance_to_route_km: number }[] {
  const hits: { id: number; name: string; road_type: string; blocked_reason: string | null; distance_to_route_km: number }[] = [];
  for (const r of roads) {
    if (r.status !== "blocked") continue;
    let geo: any;
    try {
      geo = JSON.parse(r.geojson);
    } catch {
      continue;
    }
    const lineCoords: [number, number][] = geo?.coordinates ?? [];
    if (!Array.isArray(lineCoords) || lineCoords.length === 0) continue;
    let best = Infinity;
    for (const [lon, lat] of lineCoords) {
      const d = pointToRouteDistanceKm(lat, lon, coords);
      if (d < best) best = d;
    }
    if (best <= radiusKm) {
      hits.push({ id: r.id, name: r.name, road_type: r.road_type, blocked_reason: r.blocked_reason, distance_to_route_km: Math.round(best * 10) / 10 });
    }
  }
  return hits.sort((a, b) => a.distance_to_route_km - b.distance_to_route_km);
}

/** Nearest item (by haversine distance) to a single lat/lon point, from any
 * array of real records that carry latitude/longitude — used by Route
 * Explorer to show "nearest hazard/facility to this sampled point" using
 * only real GET /map/layers rows, never invented ones. */
export function nearestByDistance<T extends { latitude: number; longitude: number }>(
  point: { lat: number; lon: number },
  items: T[]
): { item: T; distance_km: number } | null {
  if (items.length === 0) return null;
  let best: T | null = null;
  let bestDist = Infinity;
  for (const item of items) {
    const d = haversineKm(point.lat, point.lon, item.latitude, item.longitude);
    if (d < bestDist) {
      bestDist = d;
      best = item;
    }
  }
  return best ? { item: best, distance_km: Math.round(bestDist * 10) / 10 } : null;
}

/** Evenly-spaced sample of ROUTE_EXPLORER_SAMPLE_COUNT points along the real
 * route polyline (by vertex index, not by arc length — a simple, honest
 * display sampling, not a claim of exact even spacing in km). Used by both
 * Route Explorer and Route Replay so they read the same underlying points. */
export function sampleRoutePoints(coords: [number, number][], count: number = ROUTE_EXPLORER_SAMPLE_COUNT): { index: number; lat: number; lon: number }[] {
  if (coords.length === 0) return [];
  if (coords.length <= count) return coords.map((c, i) => ({ index: i, lat: c[1], lon: c[0] }));
  const out: { index: number; lat: number; lon: number }[] = [];
  for (let i = 0; i < count; i++) {
    const idx = Math.round((i * (coords.length - 1)) / (count - 1));
    out.push({ index: idx, lat: coords[idx][1], lon: coords[idx][0] });
  }
  return out;
}
