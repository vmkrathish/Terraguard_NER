import { useEffect, useState } from "react";
import { Circle, MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import "../../leafletSetup";
import { api } from "../../api/client";
import type { ImpactAssessment } from "../../types";
import ImpactPanel from "./ImpactPanel";

interface Props {
  title: string;
  lat: number;
  lon: number;
  radiusM: number;
  onClose: () => void;
}

// Focused what-if modal, backed only by the real, read-only POST /alerts/simulate
// endpoint (never mutates roads/risk_zones). Clearly labeled SIMULATION
// throughout — see ImpactPanel's banner — and the road picker only ever
// offers roads that are genuinely within the baseline impact area.
export default function ImpactSimulatorModal({ title, lat, lon, radiusM, onClose }: Props) {
  const [baseline, setBaseline] = useState<ImpactAssessment | null>(null);
  const [result, setResult] = useState<ImpactAssessment | null>(null);
  const [multiplier, setMultiplier] = useState(1);
  const [blockedRoadId, setBlockedRoadId] = useState<number | "">("");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api
      .get<ImpactAssessment>("/alerts/impact-assessment", { params: { lat, lon, radius_m: radiusM } })
      .then((r) => setBaseline(r.data))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load baseline impact"))
      .finally(() => setLoading(false));
  }, [lat, lon, radiusM]);

  const shown = result || baseline;

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { lat, lon, radius_m: radiusM, radius_multiplier: multiplier };
      if (blockedRoadId !== "") body.blocked_road_id = blockedRoadId;
      const { data } = await api.post<ImpactAssessment>("/alerts/simulate", body);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  };

  const effectiveRadius = radiusM * multiplier;

  return (
    <div className="ai-modal-backdrop" onClick={onClose}>
      <div className="ai-modal ai-modal-lg" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-header">
          <div>
            <h3 style={{ margin: 0 }}>Impact Simulator</h3>
            <div className="page-subtitle" style={{ margin: 0 }}>{title}</div>
          </div>
          <button className="ai-modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="ai-modal-body">
          {error && <div className="form-alert error">{error}</div>}
          {loading && <p className="table-empty">Loading baseline impact...</p>}

          {!loading && (
            <>
              <div className="map-container" style={{ height: "40vh", marginBottom: "var(--sp-4)" }}>
                <MapContainer center={[lat, lon]} zoom={11} style={{ height: "100%", width: "100%" }}>
                  <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  <Circle center={[lat, lon]} radius={effectiveRadius} pathOptions={{ color: "#b3342f", fillOpacity: 0.12 }} />
                  <Marker position={[lat, lon]}><Popup>Threat location</Popup></Marker>
                  {shown?.safe_zone && (
                    <Marker position={[shown.safe_zone.latitude, shown.safe_zone.longitude]}>
                      <Popup>Safe zone: {shown.safe_zone.name} ({shown.safe_zone.distance_km.toFixed(1)} km)</Popup>
                    </Marker>
                  )}
                </MapContainer>
              </div>

              <div className="grid grid-2" style={{ marginBottom: "var(--sp-4)" }}>
                <label>
                  Impact radius multiplier ({multiplier.toFixed(1)}x — {Math.round(effectiveRadius)}m)
                  <input
                    type="range"
                    min={0.5}
                    max={3}
                    step={0.1}
                    value={multiplier}
                    onChange={(e) => setMultiplier(parseFloat(e.target.value))}
                  />
                </label>
                <label>
                  What if this road is blocked?
                  <select value={blockedRoadId} onChange={(e) => setBlockedRoadId(e.target.value === "" ? "" : Number(e.target.value))}>
                    <option value="">None</option>
                    {(baseline?.affected_roads || []).map((r) => (
                      <option key={r.id} value={r.id}>{r.name} ({r.status})</option>
                    ))}
                  </select>
                </label>
              </div>

              <button className="primary" onClick={run} disabled={running}>{running ? "Running simulation..." : "Run simulation"}</button>

              {shown && (
                <div style={{ marginTop: "var(--sp-4)" }}>
                  <ImpactPanel impact={shown} />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
