import { useMemo, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import type { Marker as LeafletMarker } from "leaflet";
import "../leafletSetup";

const NER_CENTER: [number, number] = [25.8, 92.9];

// Once the browser/device has failed (or denied) a geolocation request in
// this tab, every other LocationPicker on every other page would otherwise
// show the exact same red "Couldn't get your current location" banner again
// — the permission or GPS availability hasn't changed, so repeating the
// warning on every page is just noise. Remember it for the rest of this
// browser tab (sessionStorage — cleared on close, not persisted forever),
// and only surface the banner again if a fresh attempt succeeds and later
// fails in a NEW way. The "Use current location" button itself is never
// hidden or disabled by this — the user can always retry it deliberately.
const GEO_UNAVAILABLE_KEY = "terraguard_geo_unavailable";

function hasAlreadyWarnedAboutGeo(): boolean {
  try {
    return sessionStorage.getItem(GEO_UNAVAILABLE_KEY) === "1";
  } catch {
    return false; // sessionStorage blocked (privacy mode, etc.) — fall back to always warning
  }
}

function rememberGeoUnavailable() {
  try {
    sessionStorage.setItem(GEO_UNAVAILABLE_KEY, "1");
  } catch {
    // sessionStorage blocked — nothing to persist, the banner will just show every time
  }
}

function forgetGeoUnavailable() {
  try {
    sessionStorage.removeItem(GEO_UNAVAILABLE_KEY);
  } catch {
    // ignore
  }
}

interface LocationPickerProps {
  /** Current latitude/longitude as strings (matches the surrounding form state). */
  latitude: string;
  longitude: string;
  /** Called whenever the location changes, from any source (map click, drag, GPS, typed). */
  onChange: (latitude: string, longitude: string) => void;
  /** Optional initial map center when no valid latitude/longitude is set yet. */
  defaultCenter?: [number, number];
  height?: number;
}

function parseLatLng(latitude: string, longitude: string): [number, number] | null {
  const lat = parseFloat(latitude);
  const lon = parseFloat(longitude);
  if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
    return [lat, lon];
  }
  return null;
}

// Keeps the map view in sync when the location changes from outside a map
// interaction (typed inputs, "Use current location") — MapContainer only
// honors `center` on first render otherwise.
function RecenterOnChange({ position }: { position: [number, number] | null }) {
  const map = useMap();
  useMemo(() => {
    if (position) map.setView(position, map.getZoom() < 6 ? 11 : map.getZoom());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [position?.[0], position?.[1]]);
  return null;
}

function ClickToPlace({ onPlace }: { onPlace: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onPlace(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export default function LocationPicker({ latitude, longitude, onChange, defaultCenter, height = 220 }: LocationPickerProps) {
  const [locating, setLocating] = useState(false);
  const [locateError, setLocateError] = useState<string | null>(null);

  const position = parseLatLng(latitude, longitude);
  const mapCenter = position || defaultCenter || NER_CENTER;

  function setFromCoords(lat: number, lon: number) {
    onChange(lat.toFixed(6), lon.toFixed(6));
    setLocateError(null);
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      if (!hasAlreadyWarnedAboutGeo()) {
        setLocateError("Your browser doesn't support location access.");
        rememberGeoUnavailable();
      }
      return;
    }
    setLocating(true);
    setLocateError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setFromCoords(pos.coords.latitude, pos.coords.longitude);
        setLocating(false);
        forgetGeoUnavailable(); // it works now — a later failure deserves a fresh warning
      },
      (err) => {
        setLocating(false);
        // Already told the user once this tab session that location doesn't
        // work here — the underlying reason (denied permission, no GPS in
        // this environment) hasn't changed, so silently let them keep using
        // the map instead of repeating the same banner on every page.
        if (hasAlreadyWarnedAboutGeo()) return;
        if (err.code === err.PERMISSION_DENIED) {
          setLocateError("Location access was denied. Allow it in your browser, or pick a point on the map instead.");
        } else {
          setLocateError("Couldn't get your current location. Pick a point on the map instead.");
        }
        rememberGeoUnavailable();
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  return (
    <div className="location-picker">
      <div className="location-picker-actions">
        <button type="button" className="btn btn-ghost" onClick={useCurrentLocation} disabled={locating}>
          {locating ? <span className="btn-spinner" /> : <span>📍</span>}
          {locating ? "Locating…" : "Use current location"}
        </button>
        {position && (
          <span className="location-picker-coords">
            {position[0].toFixed(5)}, {position[1].toFixed(5)}
          </span>
        )}
      </div>

      {locateError && <div className="form-alert error" style={{ margin: "8px 0" }}>{locateError}</div>}

      <div className="location-picker-map" style={{ height }}>
        <MapContainer center={mapCenter} zoom={position ? 12 : 7} style={{ height: "100%", width: "100%" }}>
          <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <ClickToPlace onPlace={setFromCoords} />
          <RecenterOnChange position={position} />
          {position && (
            <Marker
              position={position}
              draggable
              eventHandlers={{
                dragend: (e) => {
                  const marker = e.target as LeafletMarker;
                  const { lat, lng } = marker.getLatLng();
                  setFromCoords(lat, lng);
                },
              }}
            />
          )}
        </MapContainer>
      </div>
      <p className="location-picker-hint">Click the map to drop a pin, drag it to fine-tune, or use your current location above.</p>

      <details className="location-picker-manual">
        <summary>Know the exact coordinates? Enter them manually</summary>
        <div className="location-picker-manual-grid">
          <label>
            Latitude
            <input
              inputMode="decimal"
              value={latitude}
              onChange={(e) => onChange(e.target.value, longitude)}
              placeholder="e.g. 25.1667"
            />
          </label>
          <label>
            Longitude
            <input
              inputMode="decimal"
              value={longitude}
              onChange={(e) => onChange(latitude, e.target.value)}
              placeholder="e.g. 93.0167"
            />
          </label>
        </div>
      </details>
    </div>
  );
}
