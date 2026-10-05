import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import type { RiskWhatIfResponse } from "../../types";
import RiskBadge from "../RiskBadge";

// Read-only rainfall what-if slider. Calls POST /risk/predict/what-if
// (debounced ~400ms after the slider settles) — never writes to the real
// prediction state, and every result is clearly labeled SIMULATION.
export default function WhatIfSimulator({
  latitude,
  longitude,
  state,
  district,
  observationMonth,
  actualRainfallMm,
}: {
  latitude: number;
  longitude: number;
  state: string;
  district: string;
  observationMonth: number;
  actualRainfallMm: number | null;
}) {
  const hasFallback = actualRainfallMm == null || !Number.isFinite(actualRainfallMm);
  const min = hasFallback ? 0 : Math.max(0, actualRainfallMm! * 0.8);
  const max = hasFallback ? 1000 : actualRainfallMm! * 1.5;
  const defaultValue = hasFallback ? 300 : actualRainfallMm!;

  const [scenarioMm, setScenarioMm] = useState(defaultValue);
  const [result, setResult] = useState<RiskWhatIfResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const enabled = Number.isFinite(latitude) && Number.isFinite(longitude) && !!state;

  useEffect(() => {
    if (!enabled) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      setError(null);
      api
        .post<RiskWhatIfResponse>("/risk/predict/what-if", {
          latitude,
          longitude,
          state,
          district: district || undefined,
          observation_month: observationMonth,
          rainfall_month_actual_mm: hasFallback ? undefined : actualRainfallMm,
          rainfall_month_actual_mm_scenario: scenarioMm,
        })
        .then((resp) => setResult(resp.data))
        .catch((e) => setError(e instanceof Error ? e.message : "What-if simulation failed"))
        .finally(() => setLoading(false));
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioMm, latitude, longitude, state, district, observationMonth, enabled]);

  const pct = useMemo(() => ((scenarioMm - min) / (max - min || 1)) * 100, [scenarioMm, min, max]);

  if (!enabled) {
    return (
      <div className="card">
        <span className="section-label">Rainfall what-if simulator</span>
        <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 8 }}>Enter a location and state to run a rainfall simulation.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <span className="section-label">Rainfall what-if simulator</span>
      <div className="form-alert" style={{ background: "var(--gold-soft)", borderColor: "rgba(181,140,43,0.35)", color: "var(--text)", marginTop: 10 }}>
        <strong style={{ marginRight: 6 }}>SIMULATION / WHAT-IF</strong>
        Not a confirmed prediction — read-only, nothing is saved.
      </div>

      <label style={{ marginTop: 10 }}>
        Simulated monthly rainfall: {scenarioMm.toFixed(0)} mm
        <input
          type="range"
          min={min}
          max={max}
          step={1}
          value={scenarioMm}
          onChange={(e) => setScenarioMm(parseFloat(e.target.value))}
          style={{ width: "100%" }}
        />
      </label>
      <div style={{ height: 4, background: "var(--border-soft)", borderRadius: 2, marginBottom: 12, position: "relative" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent)", borderRadius: 2 }} />
      </div>

      {loading && <p style={{ color: "var(--text-dim)", fontSize: 13 }}>Simulating...</p>}
      {error && <div className="form-alert error">{error}</div>}

      {!loading && result && (
        <div className="grid grid-2">
          <div className="impact-stat">
            <div className="impact-stat-value">{result.baseline.risk_score}</div>
            <div className="impact-stat-label">Baseline risk score <RiskBadge level={result.baseline.risk_level} /></div>
            <div className="impact-stat-note">Current rainfall: {hasFallback ? "not entered" : `${actualRainfallMm} mm`}</div>
          </div>
          <div className="impact-stat">
            <div className="impact-stat-value">{result.scenario.risk_score}</div>
            <div className="impact-stat-label">Simulated risk score <RiskBadge level={result.scenario.risk_level} /></div>
            <div className="impact-stat-note">Simulated rainfall: {scenarioMm.toFixed(0)} mm</div>
          </div>
        </div>
      )}

      {!loading && result && (
        <p style={{ marginTop: 10, fontSize: 13 }}>
          Change in risk score: <b style={{ color: result.risk_score_change > 0 ? "var(--critical)" : result.risk_score_change < 0 ? "var(--low)" : "var(--text)" }}>
            {result.risk_score_change > 0 ? "+" : ""}{result.risk_score_change.toFixed(2)}
          </b>
          {result.rainfall_change_pct != null && (
            <> (rainfall change: {result.rainfall_change_pct > 0 ? "+" : ""}{result.rainfall_change_pct.toFixed(1)}%)</>
          )}
        </p>
      )}
    </div>
  );
}
