import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { MapLayers } from "../types";
import RiskBadge from "../components/RiskBadge";
import ProvenanceTag from "../components/ProvenanceTag";
import RiskLayersMap, { RISK_COLORS, type RiskLayersVisible } from "../components/gis/RiskLayersMap";
import logo from "../assets/logo-icon.png";

export default function GisMapPage() {
  const [layers, setLayers] = useState<MapLayers | null>(null);
  const [visible, setVisible] = useState<RiskLayersVisible>({
    risk_zones: true, landslide_events: true, field_reports: true,
    roads: true, villages: true, hospitals: true, schools: true,
  });

  const reload = () => api.get<MapLayers>("/map/layers").then((r) => setLayers(r.data));

  useEffect(() => {
    reload();
    // Auto-refresh after a new prediction is made anywhere in the app (see
    // PredictionPage.tsx) — a HIGH/CRITICAL prediction is saved as a real
    // risk zone, so the map should pick it up without a manual reload.
    window.addEventListener("terraguard:new-prediction", reload);
    return () => window.removeEventListener("terraguard:new-prediction", reload);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = (key: keyof typeof visible) => setVisible((v) => ({ ...v, [key]: !v[key] }));

  return (
    <div>
      <h2 className="page-title">GIS Risk Map</h2>
      <p className="page-subtitle">Risk zones, historical events, field reports, roads, villages, hospitals and schools.</p>

      <div className="card">
        <div className="gis-layers-header">
          <div className="gis-layers-title">
            <img src={logo} alt="TerraGuard NER" />
            <div>
              <h4>Layers</h4>
              <span>Select what appears on the risk map</span>
            </div>
          </div>
          <Link to="/weather" className="gis-weather-link">
            <span className="gis-weather-link-icon" aria-hidden="true">◈</span>
            <span>
              <strong>Live weather map</strong>
              <small>Open weather view <span aria-hidden="true">→</span></small>
            </span>
          </Link>
        </div>
        <div className="chip-row">
          {Object.entries(visible).map(([key, val]) => (
            <label key={key} className={`chip-toggle ${val ? "on" : ""}`}>
              <input type="checkbox" checked={val} onChange={() => toggle(key as keyof typeof visible)} />
              {key.replace(/_/g, " ")}
            </label>
          ))}
        </div>
        <h4 style={{ margin: "16px 0 10px" }}>Risk zone legend</h4>
        <div className="legend-row">
          {(["LOW", "MODERATE", "HIGH", "CRITICAL"] as const).map((level) => (
            <span className="legend-item" key={level}>
              <span className="legend-symbol" style={{ color: RISK_COLORS[level] }}>{level === "CRITICAL" ? "✚" : "▲"}</span>
              {level.charAt(0) + level.slice(1).toLowerCase()}
            </span>
          ))}
        </div>
      </div>

      <div className="map-container">
        <RiskLayersMap layers={layers} visible={visible} />
      </div>

      {layers && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Risk zone summary</h3>
          {layers.risk_zones.length === 0 && <p className="table-empty">No risk zones mapped yet.</p>}
          {layers.risk_zones.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Zone</th><th>Risk level</th><th>Score</th><th>Provenance</th></tr></thead>
                <tbody>
                  {layers.risk_zones.map((z) => (
                    <tr key={z.id}>
                      <td>{z.name}</td>
                      <td><RiskBadge level={z.risk_level} /></td>
                      <td>{z.risk_score}</td>
                      <td><ProvenanceTag provenance={z.data_provenance} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
