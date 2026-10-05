import { Fragment, useMemo } from "react";
import { GeoJSON, MapContainer, Marker, Popup, Tooltip, Circle, TileLayer } from "react-leaflet";
import L from "leaflet";
import "../../leafletSetup";
import type { MapLayers } from "../../types";
import ProvenanceTag from "../ProvenanceTag";

// Extracted verbatim from GisMapPage.tsx (no behavior change) so the same
// real Leaflet risk/infrastructure rendering can also be reused inside the
// Weather Map page's "split view" (see WeatherMapPage.tsx) — Ventusky's
// embed is a sealed third-party iframe with no API/postMessage bridge (
// confirmed: Ventusky's own FAQ states no integration/data API is offered),
// so a true single-canvas overlay of weather + risk data is not technically
// possible. Showing this real Leaflet map next to the real weather widget
// is the honest way to let a user visually compare the two.
export const NER_CENTER: [number, number] = [25.8, 92.9];

export const RISK_COLORS: Record<string, string> = {
  LOW: "#1f8a4c",
  MODERATE: "#a8790f",
  HIGH: "#c05b1e",
  CRITICAL: "#b3342f",
};

const SEVERITY_COLORS: Record<string, string> = {
  unknown: "#a8a196",
  small: "#1f8a4c",
  medium: "#a8790f",
  large: "#c05b1e",
  very_large: "#b3342f",
};
const severityColor = (s: string | null | undefined) => SEVERITY_COLORS[s || "unknown"] || SEVERITY_COLORS.unknown;
const severityRadius = (s: string | null | undefined) => {
  switch (s) {
    case "very_large": return 9;
    case "large": return 7.5;
    case "medium": return 6;
    case "small": return 5;
    default: return 4.5;
  }
};

// Item 12: distinct SVG symbols per GIS feature category, replacing generic
// dots — ported from the colleague's reference implementation. Each is a
// small inline SVG rendered as a Leaflet divIcon so it stays crisp at any
// zoom and can be colored per-feature (e.g. risk level, road-block status).
type FeatureIconKind = "risk" | "event" | "report" | "village" | "hospital" | "school";

function featureIcon(kind: FeatureIconKind, color: string, size = 30) {
  const svg = {
    risk: `<circle cx="16" cy="16" r="9" fill="${color}" fill-opacity=".9" stroke="#fff" stroke-width="2"/><circle cx="16" cy="16" r="13" fill="none" stroke="${color}" stroke-width="2" stroke-opacity=".65"/><path d="m16 10 4 8h-8l4-8Z" fill="#fff" fill-opacity=".9"/>`,
    event: `<path d="M16 3 29 28H3L16 3Z" fill="${color}" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><path d="M16 10v8M16 22v1" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>`,
    report: `<path d="M16 29s10-8.1 10-15A10 10 0 1 0 6 14c0 6.9 10 15 10 15Z" fill="${color}" stroke="#fff" stroke-width="2"/><circle cx="16" cy="14" r="3.5" fill="#fff"/>`,
    village: `<path d="M3 28V14l7-5 6 4 5-4 8 6v13H3Z" fill="${color}" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><path d="M8 28v-7h5v7M21 18h4M21 22h4" stroke="#fff" stroke-width="2"/>`,
    hospital: `<rect x="3" y="3" width="26" height="26" rx="6" fill="${color}" stroke="#fff" stroke-width="2"/><path d="M13 8h6v5h5v6h-5v5h-6v-5H8v-6h5V8Z" fill="#fff"/>`,
    school: `<path d="m3 13 13-8 13 8-13 8L3 13Z" fill="${color}" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><path d="M8 17v6c4 3 12 3 16 0v-6M28 14v8" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>`,
  }[kind];

  return L.divIcon({
    className: "gis-feature-icon",
    html: `<span class="gis-feature-icon-shape" style="--marker-color:${color};width:${size}px;height:${size}px"><svg viewBox="0 0 32 32" aria-hidden="true">${svg}</svg></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

const riskMarkerSize = (level: string) => level === "CRITICAL" ? 36 : level === "HIGH" ? 33 : 30;

export interface RiskLayersVisible {
  risk_zones: boolean;
  landslide_events: boolean;
  field_reports: boolean;
  roads: boolean;
  villages: boolean;
  hospitals: boolean;
  schools: boolean;
}

export const ALL_LAYERS_VISIBLE: RiskLayersVisible = {
  risk_zones: true, landslide_events: true, field_reports: true,
  roads: true, villages: true, hospitals: true, schools: true,
};

export default function RiskLayersMap({
  layers, visible, center = NER_CENTER, zoom = 7,
}: {
  layers: MapLayers | null;
  visible: RiskLayersVisible;
  center?: [number, number];
  zoom?: number;
}) {
  // Real per-district historical counts, keyed for O(1) popup lookup — built
  // from the backend's district_event_summary aggregate, never invented here.
  const districtStats = useMemo(() => {
    const map = new Map<string, { event_count: number; high_severity_count: number }>();
    layers?.district_event_summary.forEach((d) => {
      map.set(`${d.state}||${d.district}`, { event_count: d.event_count, high_severity_count: d.high_severity_count });
    });
    return map;
  }, [layers]);

  return (
    <MapContainer center={center} zoom={zoom} style={{ height: "100%", width: "100%" }}>
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {layers && visible.risk_zones && layers.risk_zones.map((z) => (
        <Fragment key={`rz-${z.id}`}>
          <Circle center={[z.latitude, z.longitude]} radius={z.radius_m} pathOptions={{ color: RISK_COLORS[z.risk_level] || "#888", fillOpacity: 0.25 }}>
            <Popup>
              <b>{z.name}</b><br />
              Risk: {z.risk_level} ({z.risk_score})<br />
              <ProvenanceTag provenance={z.data_provenance} />
            </Popup>
          </Circle>
          <Marker position={[z.latitude, z.longitude]} icon={featureIcon("risk", RISK_COLORS[z.risk_level] || "#888", riskMarkerSize(z.risk_level))}>
            <Tooltip>{z.name} · {z.risk_level}</Tooltip>
          </Marker>
        </Fragment>
      ))}

      {layers && visible.landslide_events && layers.landslide_events.map((e) => {
        const stats = districtStats.get(`${e.state}||${e.district}`);
        const criticalRatePct = stats && stats.event_count > 0
          ? Math.round((stats.high_severity_count / stats.event_count) * 100)
          : null;
        return (
          <Marker
            key={`ev-${e.id}`}
            position={[e.latitude, e.longitude]}
            icon={featureIcon("event", severityColor(e.severity), severityRadius(e.severity) * 2.2)}
          >
            <Tooltip>
              {e.event_title || `${e.landslide_type || "Landslide"} — ${e.district || e.state}`} ({e.severity || "unknown"})
            </Tooltip>
            <Popup>
              <b>{e.event_title || "Landslide event"}</b><br />
              Place: {e.district ? `${e.district}, ` : ""}{e.state}<br />
              Date: {e.event_date || "unknown"}<br />
              Severity: {e.severity || "unknown"}{e.trigger ? ` · Trigger: ${e.trigger}` : ""}<br />
              {e.event_description && <>{e.event_description}<br /></>}
              {(e.fatality_count != null || e.injury_count != null) && (
                <>Fatalities: {e.fatality_count ?? 0} · Injuries: {e.injury_count ?? 0}<br /></>
              )}
              {stats && (
                <>
                  District history: {stats.event_count} recorded event{stats.event_count === 1 ? "" : "s"}
                  {criticalRatePct != null && <> · {criticalRatePct}% large/very-large severity</>}<br />
                </>
              )}
              <ProvenanceTag provenance={e.data_provenance} />
            </Popup>
          </Marker>
        );
      })}

      {layers && visible.field_reports && layers.field_reports.map((r) => (
        <Marker key={`fr-${r.id}`} position={[r.latitude, r.longitude]} icon={featureIcon("report", "#187a9c")}>
          <Popup>
            <b>Field report: {r.incident_type}</b><br />
            Severity: {r.severity}<br />
            {r.description}<br />
            Sync: {r.sync_status}
          </Popup>
        </Marker>
      ))}

      {layers && visible.villages && layers.villages.map((v) => (
        <Marker key={`vg-${v.id}`} position={[v.latitude, v.longitude]} icon={featureIcon("village", "#635b9e")}>
          <Popup>
            <b>{v.name}</b> (village)<br />
            Population: {v.population ?? "unknown"}<br />
            <ProvenanceTag provenance={v.data_provenance} />
          </Popup>
        </Marker>
      ))}

      {layers && visible.hospitals && layers.hospitals.map((h) => (
        <Marker key={`hp-${h.id}`} position={[h.latitude, h.longitude]} icon={featureIcon("hospital", "#c0393b")}>
          <Popup><b>{h.name}</b> (hospital)<ProvenanceTag provenance={h.data_provenance} /></Popup>
        </Marker>
      ))}

      {layers && visible.schools && layers.schools.map((s) => (
        <Marker key={`sc-${s.id}`} position={[s.latitude, s.longitude]} icon={featureIcon("school", "#2f6b9f")}>
          <Popup><b>{s.name}</b> (school)<ProvenanceTag provenance={s.data_provenance} /></Popup>
        </Marker>
      ))}

      {layers && visible.roads && layers.roads.map((r) => {
        let geo;
        try { geo = JSON.parse(r.geojson); } catch { return null; }
        return (
          <GeoJSON
            key={`rd-${r.id}`}
            data={geo}
            style={{ color: r.status === "blocked" ? "#b3342f" : "#2c7d84", weight: 4, dashArray: r.status === "blocked" ? "6 4" : undefined }}
          />
        );
      })}
    </MapContainer>
  );
}
