import { useEffect, useState } from "react";
import { Circle, CircleMarker, GeoJSON, MapContainer, Marker, Polyline, Popup, TileLayer } from "react-leaflet";
import "../../leafletSetup";
import type { MapLayers, RouteOptimizeResponse } from "../../types";
import { NETWORK_SNAP_WARNING_KM } from "./routeMath";

const RISK_COLORS: Record<string, string> = {
  LOW: "#1f8a4c",
  MODERATE: "#a8790f",
  HIGH: "#c05b1e",
  CRITICAL: "#b3342f",
};

/** Progressively reveals `coords` (source -> destination) over a fixed
 * on-screen duration, driven by requestAnimationFrame and cancelled on
 * unmount / whenever `coords` or `replayToken` change — never a leaked
 * interval, never more than one animation running at once. This is purely
 * a reveal of the already-computed polyline (no implied live movement). */
function useRevealedPoints(coords: [number, number][], replayToken: number): [number, number][] {
  const [revealCount, setRevealCount] = useState(coords.length);

  useEffect(() => {
    if (coords.length < 2) {
      setRevealCount(coords.length);
      return;
    }
    let rafId = 0;
    const durationMs = 900; // UI animation duration, not derived from any backend timing
    const start = performance.now();
    setRevealCount(1);
    const step = (now: number) => {
      const frac = Math.min(1, (now - start) / durationMs);
      setRevealCount(Math.max(2, Math.round(frac * coords.length)));
      if (frac < 1) rafId = requestAnimationFrame(step);
    };
    rafId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coords, replayToken]);

  return coords.slice(0, revealCount);
}

interface RouteMapProps {
  center: [number, number];
  source: [number, number] | null;
  destination: [number, number] | null;
  destinationLabel: string | null;
  result: RouteOptimizeResponse | null;
  usesBlockedRoad: boolean;
  layers: MapLayers | null;
  contextRiskZoneIds: Set<number>;
  replayToken: number;
}

export default function RouteMap({
  center, source, destination, destinationLabel, result, usesBlockedRoad, layers, contextRiskZoneIds, replayToken,
}: RouteMapProps) {
  const routeCoordsLatLng: [number, number][] = result ? result.recommended_route.coordinates.map(([lon, lat]) => [lat, lon]) : [];
  const revealed = useRevealedPoints(routeCoordsLatLng, replayToken);
  const blockedRoads = layers ? layers.roads.filter((r) => r.status === "blocked") : [];

  // When the requested source/destination is meaningfully far from any
  // mapped road (TerraGuard's demo road graph is sparse), the computed
  // route actually starts/ends at the nearest graph node, not at the pin
  // itself. Rather than leave that gap invisible — which looks like the
  // route "didn't update" when you move a distant pin — draw a dashed
  // connector from the pin to where the route line really begins/ends.
  const route = result?.recommended_route;
  const routeStart = routeCoordsLatLng[0];
  const routeEnd = routeCoordsLatLng[routeCoordsLatLng.length - 1];
  const showSourceGap = !!(source && routeStart && route?.source_snap_distance_km != null && route.source_snap_distance_km > NETWORK_SNAP_WARNING_KM);
  const showDestGap = !!(destination && routeEnd && route?.destination_snap_distance_km != null && route.destination_snap_distance_km > NETWORK_SNAP_WARNING_KM);

  return (
    <div className="map-container">
      <MapContainer center={center} zoom={9} style={{ height: "100%", width: "100%" }}>
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

        {/* Risk zones from the real map layers — zones the computed route
            actually comes within their own radius_m are highlighted; the
            rest are shown lightly for map context, same as GisMapPage. */}
        {layers?.risk_zones.map((z) => (
          <Circle
            key={`rz-${z.id}`}
            center={[z.latitude, z.longitude]}
            radius={z.radius_m}
            pathOptions={{
              color: RISK_COLORS[z.risk_level] || "#888",
              fillOpacity: contextRiskZoneIds.has(z.id) ? 0.32 : 0.08,
              weight: contextRiskZoneIds.has(z.id) ? 2 : 1,
            }}
          >
            <Popup>
              <b>{z.name}</b><br />
              Risk: {z.risk_level} ({z.risk_score})
              {contextRiskZoneIds.has(z.id) && <><br /><i>Route passes within this zone's mapped radius.</i></>}
            </Popup>
          </Circle>
        ))}

        {/* Blocked-road overlay (spec section 9): every road with
            status === "blocked" in the real map layers, drawn distinctly. */}
        {blockedRoads.map((r) => {
          let geo: any;
          try {
            geo = JSON.parse(r.geojson);
          } catch {
            return null;
          }
          return (
            <GeoJSON key={`blocked-${r.id}`} data={geo} style={{ color: "#b3342f", weight: 4, dashArray: "6 4" }}>
              <Popup>
                <b>{r.name}</b> ({r.road_type})<br />
                Status: blocked<br />
                Reason: {r.blocked_reason || "No reason recorded"}
              </Popup>
            </GeoJSON>
          );
        })}

        {/* Villages/hospitals/schools give map context for where the
            destination sits relative to real facilities. */}
        {layers?.hospitals.map((h) => (
          <CircleMarker key={`hp-${h.id}`} center={[h.latitude, h.longitude]} radius={4} pathOptions={{ color: "#fff", weight: 1, fillColor: "#2c7d84", fillOpacity: 0.8 }}>
            <Popup><b>{h.name}</b> (hospital)</Popup>
          </CircleMarker>
        ))}
        {layers?.schools.map((s) => (
          <CircleMarker key={`sc-${s.id}`} center={[s.latitude, s.longitude]} radius={4} pathOptions={{ color: "#fff", weight: 1, fillColor: "#5b7fae", fillOpacity: 0.8 }}>
            <Popup><b>{s.name}</b> (school)</Popup>
          </CircleMarker>
        ))}

        {revealed.length > 1 && (
          <Polyline positions={revealed} pathOptions={{ color: usesBlockedRoad ? "#b3342f" : "#2c7d84", weight: 5 }} />
        )}

        {/* Dashed "gap" lines — honest disclosure that the route starts/ends
            at the nearest mapped road node, not exactly at the pin, when
            that gap is large (see route.*_snap_distance_km). */}
        {showSourceGap && (
          <Polyline positions={[source!, routeStart]} pathOptions={{ color: "#6b7280", weight: 2, dashArray: "3 6" }}>
            <Popup>Source is {route!.source_snap_distance_km} km from the nearest mapped road — the route starts there instead.</Popup>
          </Polyline>
        )}
        {showDestGap && (
          <Polyline positions={[routeEnd, destination!]} pathOptions={{ color: "#6b7280", weight: 2, dashArray: "3 6" }}>
            <Popup>Destination is {route!.destination_snap_distance_km} km from the nearest mapped road — the route ends there instead.</Popup>
          </Polyline>
        )}

        {source && (
          <CircleMarker center={source} radius={9} pathOptions={{ color: "#fff", weight: 2, fillColor: "#1f8a4c", fillOpacity: 1 }}>
            <Popup><b>Start</b></Popup>
          </CircleMarker>
        )}

        {destination && (
          <Marker position={destination}>
            <Popup><b>{destinationLabel || "Destination"}</b></Popup>
          </Marker>
        )}
      </MapContainer>
    </div>
  );
}
