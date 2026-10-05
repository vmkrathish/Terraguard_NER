import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Alert, ImpactAssessment, ThreatEntry } from "../types";

// Per-threat extra data the /alerts/threats list itself doesn't carry
// (population, response/lifecycle progress) — fetched lazily, one real
// backend call per threat, never invented. Used only to build the honest
// top-of-page summary cards. Population is always computed at a fixed
// 20000m radius (matching /alerts/{id} and the default /alerts/impact-assessment
// radius) so every threat's figure is on the same real, comparable basis.
export interface ThreatExtra {
  populationKnown: number | null;
  populationNote: string | null;
  assignedDone: boolean | null; // null = unknown (fetch failed / not attempted)
  resolvedDone: boolean | null;
  safeZoneDistanceKm: number | null;
  blockedRoadsCount: number;
}

export interface AlertIntelligenceState {
  threats: ThreatEntry[];
  alerts: Alert[];
  extras: Record<number, ThreatExtra>; // keyed by risk_zone_id
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  reload: () => void;
}

async function fetchExtraFor(t: ThreatEntry): Promise<ThreatExtra> {
  try {
    if (t.latest_alert) {
      const { data } = await api.get<{
        impact: ImpactAssessment;
        lifecycle: { stage: string; status: string }[];
      }>(`/alerts/${t.latest_alert.id}`);
      const stageDone = (s: string) => data.lifecycle.some((l) => l.stage === s && l.status === "done");
      return {
        populationKnown: data.impact.total_population_known,
        populationNote: data.impact.population_note,
        assignedDone: stageDone("assigned"),
        resolvedDone: stageDone("resolved"),
        safeZoneDistanceKm: data.impact.safe_zone?.distance_km ?? null,
        blockedRoadsCount: data.impact.affected_roads.filter((r) => r.status === "blocked").length,
      };
    }
    const { data } = await api.get<ImpactAssessment>("/alerts/impact-assessment", {
      params: { lat: t.latitude, lon: t.longitude, radius_m: 20000 },
    });
    return {
      populationKnown: data.total_population_known,
      populationNote: data.population_note,
      assignedDone: null,
      resolvedDone: null,
      safeZoneDistanceKm: data.safe_zone?.distance_km ?? null,
      blockedRoadsCount: data.affected_roads.filter((r) => r.status === "blocked").length,
    };
  } catch {
    return {
      populationKnown: null,
      populationNote: null,
      assignedDone: null,
      resolvedDone: null,
      safeZoneDistanceKm: null,
      blockedRoadsCount: 0,
    };
  }
}

export function useAlertIntelligence(): AlertIntelligenceState {
  const [threats, setThreats] = useState<ThreatEntry[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [extras, setExtras] = useState<Record<number, ThreatExtra>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    Promise.all([api.get<ThreatEntry[]>("/alerts/threats"), api.get<Alert[]>("/alerts")])
      .then(([t, a]) => {
        setThreats(t.data);
        setAlerts(a.data);
        setError(null);
        setLastUpdated(new Date());
        // Fire off the per-threat extra-data fetches after the board itself
        // is already rendered, so the summary cards fill in progressively
        // ("No verified data" / a spinner-less blank until they resolve)
        // rather than blocking the whole page on N extra requests.
        Promise.all(t.data.map((threat) => fetchExtraFor(threat))).then((results) => {
          const map: Record<number, ThreatExtra> = {};
          t.data.forEach((threat, i) => {
            map[threat.risk_zone_id] = results[i];
          });
          setExtras(map);
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load alert intelligence data"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { threats, alerts, extras, loading, error, lastUpdated, reload };
}
