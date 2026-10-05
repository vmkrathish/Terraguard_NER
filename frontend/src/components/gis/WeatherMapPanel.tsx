import { useMemo, useState } from "react";

// Ventusky (embed.ventusky.com) — a free, public embeddable weather map
// widget. Confirmed directly against Ventusky's own documentation and FAQ:
// there is no developer data API ("it is not possible to integrate our
// product into another application currently" / no historical-data API is
// offered), and no postMessage/JS bridge for a parent page to read or drive
// the iframe beyond its initial URL. That means this widget is a real,
// live, third-party VISUAL map — not a source of numeric data TerraGuard can
// ingest, and not something that can be composited as a true layer inside
// our own Leaflet GIS map (see RiskLayersMap.tsx for that). The `l=` layer
// parameter and the other query params below are documented/verified
// working values (my.ventusky.com's own embed how-to guide, cross-checked
// against live ventusky.com URLs) — not guessed.
const NER_PINS =
  "pin=28.2;94.7;dot;Arunachal%20Pradesh;26.14;91.74;dot;Assam;24.7;93.9;dot;Manipur;25.5;91.4;dot;Meghalaya;23.7;92.7;dot;Mizoram;26.2;94.6;dot;Nagaland;27.5;88.5;dot;Sikkim;23.9;91.9;dot;Tripura";

export interface WeatherLayerOption {
  key: string;
  label: string;
  param: string; // verified real Ventusky `l=` value
}

// Every option here was verified against a real, working Ventusky URL before
// being added — an unverifiable layer code is left out rather than guessed
// (Ventusky itself advertises "50+ layers", most of which are not
// re-verified here; these six are the ones explicitly checked).
export const WEATHER_LAYERS: WeatherLayerOption[] = [
  { key: "default", label: "Default view", param: "" },
  { key: "temperature", label: "Temperature", param: "temperature-2m" },
  { key: "rain", label: "Rain", param: "rain-1h" },
  { key: "wind", label: "Wind", param: "wind-10m" },
  { key: "clouds", label: "Clouds", param: "clouds-total" },
  { key: "pressure", label: "Pressure", param: "pressure" },
  { key: "radar", label: "Radar / precipitation", param: "radar" },
];

export default function WeatherMapPanel({
  center, zoom = 6, heightVar = "100%",
}: {
  center?: [number, number]; // [lat, lon] — defaults to the NE India regional view
  zoom?: number;
  heightVar?: string;
}) {
  const [layer, setLayer] = useState<WeatherLayerOption>(WEATHER_LAYERS[0]);
  const [loaded, setLoaded] = useState(false);

  const lat = center ? center[0] : 25.8;
  const lon = center ? center[1] : 92.9;

  const ventuskyUrl = useMemo(() => {
    const params = [`p=${lat};${lon};${zoom}`];
    if (layer.param) params.push(`l=${layer.param}`);
    // Only show the 8-state overview pins on the default regional view — a
    // prediction-centered view (a specific lat/lon passed in) is about one
    // point, so the state pins would just clutter it.
    if (!center) params.push(NER_PINS);
    return `https://embed.ventusky.com/?${params.join("&")}`;
  }, [lat, lon, zoom, layer, center]);

  return (
    <div className="weather-map-panel">
      <div className="weather-layer-row">
        {WEATHER_LAYERS.map((opt) => (
          <button
            key={opt.key}
            type="button"
            className={`chip-toggle ${layer.key === opt.key ? "on" : ""}`}
            onClick={() => { setLayer(opt); setLoaded(false); }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="weather-map-frame" style={{ height: heightVar }}>
        {!loaded && <div className="weather-map-loading">Loading live weather map…</div>}
        <iframe
          key={ventuskyUrl}
          src={ventuskyUrl}
          title="Ventusky weather map"
          style={{ width: "100%", height: "100%", border: "none", display: "block" }}
          loading="lazy"
          onLoad={() => setLoaded(true)}
        />
      </div>

      <div className="weather-map-footer">
        <span>
          <strong>Live external map</strong> · Source:{" "}
          <a href="https://www.ventusky.com" target="_blank" rel="noreferrer">Ventusky</a>
        </span>
        <span className="weather-map-footer-note">
          This is a live, third-party visual weather widget — TerraGuard does not extract numeric
          values from it, and it is not used as an input to the ML risk model. For real, numeric
          live-rainfall context, see the Prediction page's "Live conditions" panel.
        </span>
      </div>
    </div>
  );
}
