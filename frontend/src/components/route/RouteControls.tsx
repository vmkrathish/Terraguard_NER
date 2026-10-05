import { useState } from "react";
import LocationPicker from "../LocationPicker";
import type { MapLayers } from "../../types";
import { nearestByDistance } from "./routeMath";

export const EMERGENCY_TYPES: { value: string; label: string; hint: string }[] = [
  { value: "medical", label: "Medical", hint: "Routes to the nearest real hospital when using \"nearest safe zone\"." },
  { value: "evacuation", label: "Evacuation", hint: "Routes to the nearest safe zone outside HIGH/CRITICAL risk areas." },
  { value: "rescue", label: "Rescue / Fire", hint: "Strict avoidance — routes around every mapped risk zone, not just blocked roads, even if longer." },
  { value: "supply", label: "Supply / General", hint: "Standard lower-risk routing to a manually chosen destination." },
];

export interface RouteForm {
  source_lat: string;
  source_lon: string;
  dest_lat: string;
  dest_lon: string;
  emergency_type: string;
}

interface RouteControlsProps {
  form: RouteForm;
  setForm: (updater: (prev: RouteForm) => RouteForm) => void;
  toNearestSafeZone: boolean;
  setToNearestSafeZone: (v: boolean) => void;
  layers: MapLayers | null;
  loading: boolean;
  onSubmit: () => void;
}

/** Compact top control bar (spec section 3-4): From/To/Emergency type collapse
 * into single-line summaries with a "Change" toggle, instead of two
 * permanent 180px+ maps sitting beside the results at all times. */
export default function RouteControls({ form, setForm, toNearestSafeZone, setToNearestSafeZone, layers, loading, onSubmit }: RouteControlsProps) {
  const [openPicker, setOpenPicker] = useState<"source" | "dest" | null>(null);
  const hint = EMERGENCY_TYPES.find((t) => t.value === form.emergency_type)?.hint;
  const mappedPlaces = layers
    ? [
        ...layers.hospitals.map((place) => ({ ...place, kind: "hospital" })),
        ...layers.schools.map((place) => ({ ...place, kind: "school" })),
        ...layers.villages.map((place) => ({ ...place, kind: "village" })),
      ]
    : [];

  const readableLocation = (latitude: string, longitude: string) => {
    const point = { lat: parseFloat(latitude), lon: parseFloat(longitude) };
    if (!Number.isFinite(point.lat) || !Number.isFinite(point.lon)) return "Select a point";
    const nearest = nearestByDistance(point, mappedPlaces);
    return nearest && nearest.distance_km <= 25 ? `Near ${nearest.item.name}` : "Selected point";
  };

  return (
    <div className="card route-controls">
      <div className="route-controls-row">
        <div className="route-control-field">
          <span className="route-control-label">From</span>
          <button type="button" className="route-control-value" onClick={() => setOpenPicker(openPicker === "source" ? null : "source")}>
            <span className="route-control-value-summary">
              <span className="route-control-value-location">{readableLocation(form.source_lat, form.source_lon)}</span>
              <span className="route-control-value-coords">{form.source_lat}, {form.source_lon}</span>
            </span>
            <span className="route-control-edit">{openPicker === "source" ? "Select" : "Change"}</span>
          </button>
        </div>

        <div className="route-control-field">
          <span className="route-control-label">To</span>
          {toNearestSafeZone ? (
            <div className="route-control-value route-control-value-static">Nearest safe zone (auto)</div>
          ) : (
            <button type="button" className="route-control-value" onClick={() => setOpenPicker(openPicker === "dest" ? null : "dest")}>
              <span className="route-control-value-summary">
                <span className="route-control-value-location">{readableLocation(form.dest_lat, form.dest_lon)}</span>
                <span className="route-control-value-coords">{form.dest_lat}, {form.dest_lon}</span>
              </span>
              <span className="route-control-edit">{openPicker === "dest" ? "Select" : "Change"}</span>
            </button>
          )}
        </div>

        <div className="route-control-field">
          <span className="route-control-label">Emergency type</span>
          <select value={form.emergency_type} onChange={(e) => setForm((prev) => ({ ...prev, emergency_type: e.target.value }))}>
            {EMERGENCY_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>

        <button className="primary route-control-submit blue-action-button" onClick={onSubmit} disabled={loading}>
          {loading ? "Computing…" : toNearestSafeZone ? "Find & route" : "Find route"}
        </button>
      </div>

      <label className="route-control-checkbox">
        <input type="checkbox" checked={toNearestSafeZone} onChange={(e) => setToNearestSafeZone(e.target.checked)} />
        Route to nearest safe zone automatically (nearest hospital/school/village outside a HIGH or CRITICAL risk zone)
      </label>

      {hint && <p className="route-control-hint">{hint}</p>}

      {openPicker === "source" && (
        <div className="route-control-picker">
          <label>Your location (source)
            <LocationPicker
              latitude={form.source_lat}
              longitude={form.source_lon}
              onChange={(source_lat, source_lon) => setForm((prev) => ({ ...prev, source_lat, source_lon }))}
              height={220}
            />
          </label>
        </div>
      )}

      {openPicker === "dest" && !toNearestSafeZone && (
        <div className="route-control-picker">
          <label>Destination
            <LocationPicker
              latitude={form.dest_lat}
              longitude={form.dest_lon}
              onChange={(dest_lat, dest_lon) => setForm((prev) => ({ ...prev, dest_lat, dest_lon }))}
              height={220}
            />
          </label>
        </div>
      )}
    </div>
  );
}
