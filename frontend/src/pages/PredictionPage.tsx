import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { GeoReverseResponse, RainfallCurrentResponse, RainfallShockResponse, RiskPredictResponse } from "../types";
import LocationPicker from "../components/LocationPicker";
import LiveRiskPulse from "../components/prediction/LiveRiskPulse";
import GroundedCaption from "../components/prediction/GroundedCaption";
import WhyThisPrediction from "../components/prediction/WhyThisPrediction";
import BaselineComparison from "../components/prediction/BaselineComparison";
import LiveConditionsPanel from "../components/prediction/LiveConditionsPanel";
import RiskTimeline from "../components/prediction/RiskTimeline";
import AnomalyPanel from "../components/prediction/AnomalyPanel";
import ImpactSection from "../components/prediction/ImpactSection";
import WhatIfSimulator from "../components/prediction/WhatIfSimulator";
import EvidenceSection from "../components/prediction/EvidenceSection";
import OperationalActions from "../components/prediction/OperationalActions";

const STATES = ["Assam", "Sikkim", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Tripura", "Arunachal Pradesh"];

// Observation month is shown to the user as a month name, but stored/sent
// as its numeric value (1-12) — the API expects an integer.
const MONTHS = [
  { value: 1, label: "January" }, { value: 2, label: "February" }, { value: 3, label: "March" },
  { value: 4, label: "April" }, { value: 5, label: "May" }, { value: 6, label: "June" },
  { value: 7, label: "July" }, { value: 8, label: "August" }, { value: 9, label: "September" },
  { value: 10, label: "October" }, { value: 11, label: "November" }, { value: 12, label: "December" },
];

// Captures exactly what was submitted for a prediction, so the intelligence
// panels below the result stay consistent with the query that produced it
// even if the user keeps editing the (now de-emphasized) query form.
interface SubmittedQuery {
  latitude: number;
  longitude: number;
  state: string;
  district: string;
  observation_month: number;
  rainfall_month_actual_mm: number | null;
}

export default function PredictionPage() {
  const [form, setForm] = useState({
    latitude: "25.1667", longitude: "93.0167", state: "Assam", district: "Dima Hasao",
    observation_month: "7", rainfall_month_actual_mm: "450",
  });
  const [result, setResult] = useState<RiskPredictResponse | null>(null);
  const [submitted, setSubmitted] = useState<SubmittedQuery | null>(null);
  const [analyzedAt, setAnalyzedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [locateNote, setLocateNote] = useState<string | null>(null);
  const geoRequestId = useRef(0);

  const [shock, setShock] = useState<RainfallShockResponse | null>(null);
  const [shockLoading, setShockLoading] = useState(false);

  const [liveConditions, setLiveConditions] = useState<RainfallCurrentResponse | null>(null);
  const [liveConditionsLoading, setLiveConditionsLoading] = useState(false);

  // Whenever the pinned location changes (map click/drag, "use current
  // location", or a typed coordinate), look up its state/district
  // automatically instead of leaving the user to type them separately —
  // debounced so a drag across the map doesn't fire a lookup per pixel.
  useEffect(() => {
    const lat = parseFloat(form.latitude);
    const lon = parseFloat(form.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

    const requestId = ++geoRequestId.current;
    setLocating(true);
    setLocateNote(null);
    const timer = setTimeout(async () => {
      try {
        const resp = await api.get<GeoReverseResponse>("/geo/reverse", { params: { lat, lon } });
        if (requestId !== geoRequestId.current) return; // a newer pin superseded this lookup
        if (resp.data.found && resp.data.state) {
          setForm((prev) => ({ ...prev, state: resp.data.state as string, district: resp.data.district || prev.district }));
        } else {
          setLocateNote("Couldn't match this location to one of the 8 covered states — set State manually if needed.");
        }
      } catch {
        if (requestId !== geoRequestId.current) return;
        setLocateNote("Couldn't look up the state for this location automatically — set it manually.");
      } finally {
        if (requestId === geoRequestId.current) setLocating(false);
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, 500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.latitude, form.longitude]);

  // Real "current vs. historical baseline" comparison — fetched once a
  // prediction has been submitted, using the exact query that was submitted
  // (not whatever the form has since drifted to). Never blocks the predict
  // button itself.
  useEffect(() => {
    if (!submitted || !submitted.state) {
      setShock(null);
      return;
    }
    let cancelled = false;
    setShockLoading(true);
    api
      .get<RainfallShockResponse>("/rainfall/shock", {
        params: { state: submitted.state, district: submitted.district || undefined, month: submitted.observation_month },
      })
      .then((resp) => !cancelled && setShock(resp.data))
      .catch(() => !cancelled && setShock(null))
      .finally(() => !cancelled && setShockLoading(false));
    return () => {
      cancelled = true;
    };
  }, [submitted]);

  // Live/current rainfall from the external data-source orchestrator (cache
  // -> IMD -> NASA POWER, honest insufficient_data fallback) — a small bonus
  // panel, never blocking. Fetched once a prediction has been submitted,
  // same trigger point as the baseline comparison above.
  useEffect(() => {
    if (!submitted) {
      setLiveConditions(null);
      return;
    }
    let cancelled = false;
    setLiveConditionsLoading(true);
    api
      .get<RainfallCurrentResponse>("/rainfall/current", {
        params: { lat: submitted.latitude, lon: submitted.longitude },
      })
      .then((resp) => !cancelled && setLiveConditions(resp.data))
      .catch(() => !cancelled && setLiveConditions(null))
      .finally(() => !cancelled && setLiveConditionsLoading(false));
    return () => {
      cancelled = true;
    };
  }, [submitted]);

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      const latitude = parseFloat(form.latitude);
      const longitude = parseFloat(form.longitude);
      const observation_month = parseInt(form.observation_month);
      const rainfall_month_actual_mm = form.rainfall_month_actual_mm ? parseFloat(form.rainfall_month_actual_mm) : undefined;
      const resp = await api.post<RiskPredictResponse>("/risk/predict", {
        latitude,
        longitude,
        state: form.state,
        district: form.district || undefined,
        observation_month,
        rainfall_month_actual_mm,
      });
      setResult(resp.data);
      setAnalyzedAt(new Date());
      setSubmitted({
        latitude,
        longitude,
        state: form.state,
        district: form.district,
        observation_month,
        rainfall_month_actual_mm: rainfall_month_actual_mm ?? null,
      });
      // A HIGH/CRITICAL prediction is now also saved as a real risk zone
      // (see backend api/risk.py) — this event tells any open GIS Map or
      // Dashboard tab to refetch, so the new zone shows up without a manual
      // page reload.
      window.dispatchEvent(new CustomEvent("terraguard:new-prediction", { detail: resp.data }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="page-title">Landslide Risk Intelligence Center</h2>
      <p className="page-subtitle">ML-based prediction with explainability, evidence, impact and rainfall context — all traced to real backend data.</p>

      <div className={`grid prediction-workspace ${result ? "result-ready" : "result-pending"}`}>
        <div className="card" style={result ? { fontSize: 13 } : undefined}>
          <h3>Query</h3>
          <label>Location
            <LocationPicker
              latitude={form.latitude}
              longitude={form.longitude}
              onChange={(latitude, longitude) => setForm({ ...form, latitude, longitude })}
            />
          </label>
          <label>State {locating && <span style={{ color: "var(--text-dim)", fontWeight: 400, fontSize: 12 }}>(looking up from pin...)</span>}
            <select value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })}>
              {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>District (optional)
            <input value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })} />
          </label>
          {locateNote && (
            <div className="form-alert" style={{ marginTop: -6, marginBottom: 14, fontSize: 12 }}>{locateNote}</div>
          )}
          <label>Observation month
            <select value={form.observation_month} onChange={(e) => setForm({ ...form, observation_month: e.target.value })}>
              {MONTHS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </label>
          <label>Actual monthly rainfall (mm, optional)
            <input value={form.rainfall_month_actual_mm} onChange={(e) => setForm({ ...form, rainfall_month_actual_mm: e.target.value })} />
          </label>
          <button className="primary predict-risk-button" onClick={submit} disabled={loading}>
            {loading ? "Predicting..." : "Predict risk"}
          </button>
          {error && <div className="form-alert error" style={{ marginTop: 14, marginBottom: 0 }}>{error}</div>}
        </div>

        {result && submitted && (
          <div className="prediction-result-card" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
            <LiveRiskPulse result={result} analyzedAt={analyzedAt ?? new Date()} shock={shock} />
            <GroundedCaption result={result} shock={shock} />
            <AnomalyPanel anomaly={result.environmental_anomaly} />
          </div>
        )}
      </div>

      {!result && (
        <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 20 }}>
          Run a prediction to see explainability, evidence, impact assessment, rainfall trends and a rainfall what-if simulator.
        </p>
      )}

      {/* The rainfall what-if simulator is read-only and doesn't require an
          existing prediction, but is only rendered once there's at least a
          location + state to avoid a meaningless call. */}
      {!result && form.state && (
        <div style={{ marginTop: 20 }}>
          <WhatIfSimulator
            latitude={parseFloat(form.latitude)}
            longitude={parseFloat(form.longitude)}
            state={form.state}
            district={form.district}
            observationMonth={parseInt(form.observation_month)}
            actualRainfallMm={form.rainfall_month_actual_mm ? parseFloat(form.rainfall_month_actual_mm) : null}
          />
        </div>
      )}

      {result && submitted && (
        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
          <WhyThisPrediction result={result} />

          <div className="grid grid-2">
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
              <BaselineComparison shock={shock} loading={shockLoading} />
              <LiveConditionsPanel current={liveConditions} loading={liveConditionsLoading} />
            </div>
            <RiskTimeline
              state={submitted.state}
              district={submitted.district}
              month={submitted.observation_month}
              latitude={submitted.latitude}
              longitude={submitted.longitude}
            />
          </div>

          <ImpactSection result={result} latitude={submitted.latitude} longitude={submitted.longitude} />

          <EvidenceSection
            latitude={submitted.latitude}
            longitude={submitted.longitude}
            state={submitted.state}
            district={submitted.district}
          />

          <WhatIfSimulator
            latitude={submitted.latitude}
            longitude={submitted.longitude}
            state={submitted.state}
            district={submitted.district}
            observationMonth={submitted.observation_month}
            actualRainfallMm={submitted.rainfall_month_actual_mm}
          />

          <OperationalActions riskLevel={result.risk_level} latitude={submitted.latitude} longitude={submitted.longitude} />
        </div>
      )}
    </div>
  );
}
