import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { MapLayers, RouteOptimizeResponse } from "../types";
import RouteControls, { EMERGENCY_TYPES, type RouteForm } from "../components/route/RouteControls";
import RouteMap from "../components/route/RouteMap";
import RouteIntelligencePanel from "../components/route/RouteIntelligencePanel";
import RouteDecisionBreakdown from "../components/route/RouteDecisionBreakdown";
import RouteContextPanel from "../components/route/RouteContextPanel";
import RouteExplorer from "../components/route/RouteExplorer";
import RouteReplayButton from "../components/route/RouteReplayButton";
import CalculationTrace, { buildTraceStages } from "../components/route/CalculationTrace";
import AnalyzingChecklist from "../components/route/AnalyzingChecklist";
import { RouteStatusChip, type RouteStatusKind } from "../components/route/RouteStatus";
import { findBlockedRoadsNearRoute, findEventsNearRoute, findRiskZonesNearRoute } from "../components/route/routeMath";

const STRICT_AVOIDANCE_TYPES = new Set(["rescue", "fire"]);

export default function EmergencyRoutePage() {
  const [form, setForm] = useState<RouteForm>({
    source_lat: "25.1667", source_lon: "93.0167", dest_lat: "25.0333", dest_lon: "93.5000", emergency_type: "medical",
  });
  const [toNearestSafeZone, setToNearestSafeZone] = useState(false);
  const [result, setResult] = useState<RouteOptimizeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState<MapLayers | null>(null);
  const [replayToken, setReplayToken] = useState(0);

  const formRef = useRef(form);
  const toNearestSafeZoneRef = useRef(toNearestSafeZone);
  formRef.current = form;
  toNearestSafeZoneRef.current = toNearestSafeZone;

  // Guards against an out-of-order network response overwriting a newer
  // one. If the user changes the destination and clicks "Find route" again
  // before the FIRST request finishes, the first (older) response can still
  // arrive after the second (newer) one and silently overwrite it with a
  // stale route. Only the response matching the most recently *sent*
  // request is ever applied to state — and it is applied as ONE atomic
  // `setResult(...)` call, so distance/risk/coordinates/markers/blocked-road
  // info/safe-zone destination/emergency type can never update as separate
  // pieces of state that land at different times.
  const requestIdRef = useRef(0);

  // Real map context (risk zones, roads, villages, hospitals, schools) —
  // fetched once on load and refreshed whenever a new prediction elsewhere
  // in the app may have changed it, same pattern as GisMapPage.tsx.
  const loadLayers = () => api.get<MapLayers>("/map/layers").then((r) => setLayers(r.data)).catch(() => {});
  useEffect(() => {
    loadLayers();
  }, []);

  const submit = async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const f = formRef.current;
      const payload: Record<string, unknown> = {
        source_lat: parseFloat(f.source_lat),
        source_lon: parseFloat(f.source_lon),
        emergency_type: f.emergency_type,
      };
      if (toNearestSafeZoneRef.current) {
        payload.to_nearest_safe_zone = true;
      } else {
        payload.dest_lat = parseFloat(f.dest_lat);
        payload.dest_lon = parseFloat(f.dest_lon);
      }
      const resp = await api.post<RouteOptimizeResponse>("/route/optimize", payload);
      if (requestId !== requestIdRef.current) return; // a newer request has already superseded this one
      setResult(resp.data);
      setReplayToken((t) => t + 1);
    } catch (e) {
      if (requestId !== requestIdRef.current) return;
      setError(e instanceof Error ? e.message : "Could not compute a route.");
      setResult(null);
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  };

  // If a route is already on screen and a new HIGH/CRITICAL prediction
  // happens elsewhere in the app (a new risk zone), recompute automatically
  // so the shown route reflects the latest known risk — instead of silently
  // going stale until the user notices and resubmits by hand.
  useEffect(() => {
    const onNewPrediction = () => {
      loadLayers();
      if (result) submit();
    };
    window.addEventListener("terraguard:new-prediction", onNewPrediction);
    return () => window.removeEventListener("terraguard:new-prediction", onNewPrediction);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  const usesBlockedRoad = result?.recommended_route.label.toLowerCase().includes("blocked") ?? false;
  const strictAvoidance = STRICT_AVOIDANCE_TYPES.has(form.emergency_type);
  const emergencyLabel = EMERGENCY_TYPES.find((t) => t.value === form.emergency_type)?.label ?? form.emergency_type;

  const source: [number, number] | null = useMemo(() => {
    const lat = parseFloat(form.source_lat);
    const lon = parseFloat(form.source_lon);
    return Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null;
  }, [form.source_lat, form.source_lon]);

  const destination: [number, number] | null = useMemo(() => {
    if (result?.destination_safe_zone) return [result.destination_safe_zone.latitude, result.destination_safe_zone.longitude];
    if (result && !toNearestSafeZone) {
      const lat = parseFloat(form.dest_lat);
      const lon = parseFloat(form.dest_lon);
      return Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null;
    }
    return null;
  }, [result, toNearestSafeZone, form.dest_lat, form.dest_lon]);

  // Real geometric context: which mapped risk zones/blocked roads/historical
  // events actually lie near the computed route. Recomputed only when the
  // route or the map layers change.
  const routeContext = useMemo(() => {
    if (!result || !layers) return { riskZoneHits: [], eventHits: [], blockedRoadHits: [] };
    const coords = result.recommended_route.coordinates;
    return {
      riskZoneHits: findRiskZonesNearRoute(coords, layers.risk_zones),
      eventHits: findEventsNearRoute(coords, layers.landslide_events),
      blockedRoadHits: findBlockedRoadsNearRoute(coords, layers.roads),
    };
  }, [result, layers]);

  const contextRiskZoneIds = useMemo(() => new Set(routeContext.riskZoneHits.map((z) => z.id)), [routeContext]);

  const status: RouteStatusKind = error
    ? "error"
    : loading
    ? "analyzing"
    : result
    ? (usesBlockedRoad || result.destination_safe_zone?.inside_risk_zone) ? "caution" : "found"
    : "idle";

  const statusExplanation = (() => {
    if (error) return error;
    if (loading) return "Computing the lowest-cost route for the selected source, destination and emergency type.";
    if (!result) return "Set a source and destination, then find a route.";
    if (usesBlockedRoad && result.destination_safe_zone?.inside_risk_zone) {
      return "This route crosses a blocked road, and the destination is still inside a mapped risk zone.";
    }
    if (usesBlockedRoad) return "This route crosses a currently blocked road — no fully clear alternative was found.";
    if (result.destination_safe_zone?.inside_risk_zone) return "The nearest available destination is still inside a mapped risk zone.";
    return `Route computed: ${result.recommended_route.distance_km} km, risk score ${result.recommended_route.risk_score}/100.`;
  })();

  const center: [number, number] = source ?? [25.8, 92.9];
  const destinationLabel = result?.destination_safe_zone
    ? `${result.destination_safe_zone.name} (${result.destination_safe_zone.type})`
    : "Destination";

  return (
    <div>
      <div className="route-page-header">
        <div>
          <h2 className="page-title">Emergency Route Center</h2>
          <p className="page-subtitle">Plan a safer route using mapped roads, hazards, and emergency constraints.</p>
        </div>
        {status !== "idle" && <RouteStatusChip status={status} />}
      </div>

      <details className="route-logic">
        <summary>Routing logic</summary>
        <p>Cost = distance + risk penalty (risk score × 0.15 km/point) + blocked-road penalty (50 km per unavoidable blocked segment). TerraGuard avoids currently blocked roads whenever a clear alternative exists.</p>
      </details>

      <RouteControls
        form={form}
        setForm={setForm}
        toNearestSafeZone={toNearestSafeZone}
        setToNearestSafeZone={setToNearestSafeZone}
        layers={layers}
        loading={loading}
        onSubmit={submit}
      />

      {error && <div className="form-alert error" style={{ marginBottom: 16 }}>{error}</div>}
      {loading && <div className="card"><AnalyzingChecklist /></div>}

      <div className="route-main-grid">
        <div className="route-map-col">
          <RouteMap
            center={center}
            source={source}
            destination={destination}
            destinationLabel={destinationLabel}
            result={result}
            usesBlockedRoad={usesBlockedRoad}
            layers={layers}
            contextRiskZoneIds={contextRiskZoneIds}
            replayToken={replayToken}
          />
          {result && <RouteReplayButton onReplay={() => setReplayToken((t) => t + 1)} />}
        </div>

        <div className="route-intel-col">
          {result ? (
            <RouteIntelligencePanel
              result={result}
              status={status}
              statusExplanation={statusExplanation}
              usesBlockedRoad={usesBlockedRoad}
              emergencyLabel={emergencyLabel}
              strictAvoidance={strictAvoidance}
              nearRouteRiskZoneCount={routeContext.riskZoneHits.length}
            />
          ) : (
            !loading && (
              <div className="card">
                <h3>Route Intelligence</h3>
                <p style={{ color: "var(--text-dim)" }}>Submit a source/destination above to compute a route.</p>
              </div>
            )
          )}
        </div>
      </div>

      {result && (
        <>
          <RouteDecisionBreakdown recommended={result.recommended_route} alternative={result.alternative_route} />
          <RouteContextPanel
            riskZoneHits={routeContext.riskZoneHits}
            eventHits={routeContext.eventHits}
            blockedRoadHits={routeContext.blockedRoadHits}
          />
          <RouteExplorer result={result} layers={layers} />
          <div className="card">
            <CalculationTrace stages={buildTraceStages(result, strictAvoidance)} />
          </div>
        </>
      )}
    </div>
  );
}
