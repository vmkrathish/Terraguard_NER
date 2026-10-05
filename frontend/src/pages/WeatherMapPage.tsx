import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { MapLayers } from "../types";
import WeatherMapPanel from "../components/gis/WeatherMapPanel";
import RiskLayersMap, { ALL_LAYERS_VISIBLE } from "../components/gis/RiskLayersMap";

type ViewMode = "weather" | "split";

export default function WeatherMapPage() {
  const [searchParams] = useSearchParams();
  const [mode, setMode] = useState<ViewMode>("weather");
  const [layers, setLayers] = useState<MapLayers | null>(null);

  // A prediction can optionally deep-link here with its own coordinates (see
  // OperationalActions.tsx) so the analyst can look at live weather for the
  // exact location just predicted, rather than the generic NE-region view.
  const latParam = searchParams.get("lat");
  const lonParam = searchParams.get("lon");
  const center: [number, number] | undefined =
    latParam && lonParam && !Number.isNaN(Number(latParam)) && !Number.isNaN(Number(lonParam))
      ? [Number(latParam), Number(lonParam)]
      : undefined;

  useEffect(() => {
    if (mode === "split" && !layers) {
      api.get<MapLayers>("/map/layers").then((r) => setLayers(r.data)).catch(() => setLayers(null));
    }
  }, [mode, layers]);

  return (
    <div>
      <h2 className="page-title">Weather Monitoring</h2>
      <p className="page-subtitle">
        Live weather conditions across the North-East Region{center ? " for the selected prediction location" : ""}.
        This is an independent observation layer — it does not feed the ML risk model.
      </p>

      <div className="card">
        <div className="view-mode-row">
          <button type="button" className={`chip-toggle ${mode === "weather" ? "on" : ""}`} onClick={() => setMode("weather")}>
            Weather map
          </button>
          <button type="button" className={`chip-toggle ${mode === "split" ? "on" : ""}`} onClick={() => setMode("split")}>
            Split view: Weather + Risk map
          </button>
        </div>

        {mode === "weather" && <WeatherMapPanel center={center} zoom={center ? 8 : 6} heightVar="560px" />}

        {mode === "split" && (
          <div className="weather-split-grid">
            <div>
              <span className="section-label">Live weather</span>
              <div style={{ marginTop: 8 }}>
                <WeatherMapPanel center={center} zoom={center ? 8 : 6} heightVar="480px" />
              </div>
            </div>
            <div>
              <span className="section-label">Landslide risk &amp; infrastructure (GIS)</span>
              <div className="map-container" style={{ height: 480, marginTop: 8 }}>
                <RiskLayersMap layers={layers} visible={ALL_LAYERS_VISIBLE} center={center} zoom={center ? 9 : 7} />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <span className="section-label">About this view</span>
        <p style={{ marginTop: 8, fontSize: 13, color: "var(--text-dim)" }}>
          The weather panel is a live, third-party visual widget (Ventusky) with no data API — TerraGuard cannot and
          does not read numeric values out of it, and it never feeds the ML risk model. The risk map alongside it
          shows TerraGuard's own historical landslide events, risk zones and infrastructure, drawn from real recorded
          data. Viewing them side by side lets you visually compare current weather conditions against known risk —
          it is not a combined weather+risk calculation.
        </p>
      </div>
    </div>
  );
}
