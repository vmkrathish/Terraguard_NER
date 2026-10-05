import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Alert, FieldReport, MapLayers } from "../types";

export interface DashboardData {
  layers: MapLayers | null;
  alerts: Alert[];
  health: Record<string, unknown> | null;
  reports: FieldReport[];
  error: string | null;
  loading: boolean;
}

// Shared data source for all three role dashboards (Field Officer, Authority,
// Admin) — every widget on every dashboard is built only from these real
// API responses, never invented client-side. Each dashboard just chooses
// which parts of this same data to show and how to lay them out.
// (Model evaluation metrics were removed from every dashboard at the user's
// explicit request, so this hook no longer fetches /risk/model-metrics —
// see AdminDashboardPage.tsx and LiveRiskPulse.tsx too.)
export function useDashboardData(): DashboardData {
  const [layers, setLayers] = useState<MapLayers | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [reports, setReports] = useState<FieldReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = () =>
    Promise.all([
      api.get<MapLayers>("/map/layers"),
      api.get<Alert[]>("/alerts", { params: { limit: 8 } }),
      api.get("/health"),
      api.get<FieldReport[]>("/reports", { params: { limit: 20 } }),
    ])
      .then(([l, a, h, r]) => {
        setLayers(l.data);
        setAlerts(a.data);
        setHealth(h.data);
        setReports(r.data);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

  useEffect(() => {
    reload();
    // Auto-refresh after a new prediction anywhere in the app (see
    // PredictionPage.tsx) so counts and zone data stay current without a
    // manual page reload.
    window.addEventListener("terraguard:new-prediction", reload);
    return () => window.removeEventListener("terraguard:new-prediction", reload);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { layers, alerts, health, reports, error, loading };
}
