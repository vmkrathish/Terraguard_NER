import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { LandslideEvent, RainfallRecord, RainfallRecordsResponse } from "../../types";
import { haversineKm } from "../../utils/geo";

const NEARBY_RADIUS_KM = 50;

// Real multi-year rainfall trend for the selected month (client-filtered from
// GET /rainfall) plus a real nearby historical landslide event list
// (client-filtered from GET /landslides by haversine distance, since the
// endpoint has no lat/lon/radius filter of its own). Both show an honest
// "not enough data" state rather than ever fabricating a missing year/event.
export default function RiskTimeline({
  state,
  district,
  month,
  latitude,
  longitude,
}: {
  state: string;
  district: string;
  month: number;
  latitude: number;
  longitude: number;
}) {
  const [rainfallYears, setRainfallYears] = useState<{ year: number; rainfall_mm: number | null }[] | null>(null);
  const [rainfallLoading, setRainfallLoading] = useState(true);
  const [nearbyEvents, setNearbyEvents] = useState<LandslideEvent[] | null>(null);
  const [eventsLoading, setEventsLoading] = useState(true);

  useEffect(() => {
    if (!state) {
      setRainfallYears(null);
      setRainfallLoading(false);
      return;
    }
    let cancelled = false;
    setRainfallLoading(true);
    api
      .get<RainfallRecordsResponse>("/rainfall", { params: { state, district: district || undefined, limit: 500 } })
      .then((resp) => {
        if (cancelled) return;
        const forMonth = resp.data.records
          .filter((r: RainfallRecord) => r.month === month)
          .sort((a, b) => a.year - b.year);
        setRainfallYears(forMonth);
      })
      .catch(() => !cancelled && setRainfallYears(null))
      .finally(() => !cancelled && setRainfallLoading(false));
    return () => {
      cancelled = true;
    };
  }, [state, district, month]);

  useEffect(() => {
    if (!state || !Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      setNearbyEvents(null);
      setEventsLoading(false);
      return;
    }
    let cancelled = false;
    setEventsLoading(true);
    api
      .get<LandslideEvent[]>("/landslides", { params: { state, limit: 500 } })
      .then((resp) => {
        if (cancelled) return;
        const nearby = resp.data
          .filter((e) => haversineKm(latitude, longitude, e.latitude, e.longitude) <= NEARBY_RADIUS_KM)
          .sort((a, b) => (b.event_date || "").localeCompare(a.event_date || ""));
        setNearbyEvents(nearby);
      })
      .catch(() => !cancelled && setNearbyEvents(null))
      .finally(() => !cancelled && setEventsLoading(false));
    return () => {
      cancelled = true;
    };
  }, [state, latitude, longitude]);

  const distinctYears = new Set((rainfallYears || []).filter((r) => r.rainfall_mm != null).map((r) => r.year));
  const maxRainfall = Math.max(...(rainfallYears || []).map((r) => r.rainfall_mm ?? 0), 1);

  return (
    <div className="card">
      <span className="section-label">Rainfall trend &amp; historical events</span>

      <h4 style={{ marginTop: 10 }}>Multi-year rainfall for this month</h4>
      {rainfallLoading && <p style={{ color: "var(--text-dim)", fontSize: 13 }}>Loading rainfall history...</p>}
      {!rainfallLoading && distinctYears.size < 2 && (
        <p style={{ color: "var(--text-dim)", fontSize: 13 }}>Insufficient historical observations for this month/district.</p>
      )}
      {!rainfallLoading && distinctYears.size >= 2 && rainfallYears && (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 90, marginBottom: 8 }}>
          {rainfallYears.map((r) => (
            <div key={r.year} style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: 1, minWidth: 0 }}>
              <div
                title={`${r.year}: ${r.rainfall_mm ?? "no data"} mm`}
                style={{
                  width: "100%",
                  maxWidth: 28,
                  height: `${r.rainfall_mm == null ? 2 : Math.max(3, (r.rainfall_mm / maxRainfall) * 70)}px`,
                  background: r.rainfall_mm == null ? "var(--border-soft)" : "var(--accent)",
                  borderRadius: "3px 3px 0 0",
                }}
              />
              <span style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>{r.year}</span>
            </div>
          ))}
        </div>
      )}

      <h4>Nearby historical landslide events (within {NEARBY_RADIUS_KM}km)</h4>
      {eventsLoading && <p style={{ color: "var(--text-dim)", fontSize: 13 }}>Loading historical events...</p>}
      {!eventsLoading && (!nearbyEvents || nearbyEvents.length === 0) && (
        <p className="table-empty" style={{ margin: 0 }}>No nearby historical events on record.</p>
      )}
      {!eventsLoading && nearbyEvents && nearbyEvents.length > 0 && (
        <ul className="impact-list" style={{ maxHeight: 220, overflowY: "auto" }}>
          {nearbyEvents.map((e) => (
            <li key={e.id}>
              <b>{e.event_date || "date unknown"}</b> — {e.landslide_type || "type unknown"}, severity {e.severity || "unknown"}
              {e.fatality_count != null && e.fatality_count > 0 ? `, ${e.fatality_count} fatalities` : ""}
              {" "}({e.district || e.state || "location unknown"})
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
