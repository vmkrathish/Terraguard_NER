import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { VillageCensusCoverage, VillageCensusSearchResponse } from "../types";

export default function VillageDataPage() {
  const [coverage, setCoverage] = useState<VillageCensusCoverage | null>(null);
  const [state, setState] = useState("");
  const [villageName, setVillageName] = useState("");
  const [includeSynthetic, setIncludeSynthetic] = useState(false);
  const [result, setResult] = useState<VillageCensusSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadCoverage = () =>
    api.get<VillageCensusCoverage>("/villages/census-profile/coverage").then((r) => setCoverage(r.data));

  useEffect(() => {
    loadCoverage();
  }, []);

  const search = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { limit: "50", include_synthetic: String(includeSynthetic) };
      if (state) params.state = state;
      if (villageName) params.village_name = villageName;
      const r = await api.get<VillageCensusSearchResponse>("/villages/census-profile", { params });
      setResult(r.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    search();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeSynthetic]);

  return (
    <div>
      <h2 className="page-title">Village Data (Census 2001)</h2>
      <p className="page-subtitle">
        Census of India 2001 Village Directory — population, households, and infrastructure
        exposure context for villages across 7 North-Eastern states. This is context data only:
        it has no coordinates and never feeds the ML risk model (see coverage note below).
      </p>

      {coverage && (
        <div className="card">
          <h3>Dataset coverage</h3>
          <p>
            Source: {coverage.source} ({coverage.census_year}). Not covered:{" "}
            {coverage.states_not_covered.join(", ") || "none"}.
          </p>
          <table>
            <thead>
              <tr>
                <th>State</th>
                <th>Villages</th>
                <th>Total population</th>
              </tr>
            </thead>
            <tbody>
              {coverage.states_covered.map((row) => (
                <tr key={row.state_name}>
                  <td>{row.state_name}</td>
                  <td>{row.villages.toLocaleString()}</td>
                  <td>{row.population_total?.toLocaleString() ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 12, color: "#6b7280" }}>
            Total real villages loaded: {coverage.states_covered.reduce((sum, r) => sum + r.villages, 0).toLocaleString()}
            {coverage.synthetic_villages_available > 0 && (
              <> · {coverage.synthetic_villages_available.toLocaleString()} additional synthetic (statistically modeled, not real) villages available — see the toggle below.</>
            )}
          </p>
        </div>
      )}

      <div className="card">
        <h3>Search villages</h3>
        <label>
          State
          <input value={state} onChange={(e) => setState(e.target.value)} placeholder="e.g. Assam" />
        </label>
        <label>
          Village name contains
          <input value={villageName} onChange={(e) => setVillageName(e.target.value)} placeholder="e.g. Dima" />
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: "normal" }}>
          <input
            type="checkbox"
            checked={includeSynthetic}
            onChange={(e) => setIncludeSynthetic(e.target.checked)}
          />
          Include synthetic villages (statistically modeled, not real Census records)
        </label>
        <button className="primary blue-action-button" onClick={search} disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>

        {result && (
          <>
            <p>
              {result.matched} record{result.matched === 1 ? "" : "s"} matched.
              {result.note && <> {result.note}</>}
            </p>
            <div style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th>Village</th>
                    <th>State</th>
                    <th>Population</th>
                    <th>Households</th>
                    <th>Nearest town</th>
                    <th>Distance (km)</th>
                    {includeSynthetic && <th>Source</th>}
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((v) => (
                    <tr key={v.record_id}>
                      <td>{v.village_name}</td>
                      <td>{v.state_name}</td>
                      <td>{v.population_total ?? "–"}</td>
                      <td>{v.total_households ?? "–"}</td>
                      <td>{v.nearest_town_name ?? "–"}</td>
                      <td>{v.distance_to_town_km ?? "–"}</td>
                      {includeSynthetic && (
                        <td>
                          {v.data_provenance === "synthetic_generated_v1" ? (
                            <span style={{ color: "#b45309", fontWeight: 600 }}>Synthetic</span>
                          ) : (
                            <span style={{ color: "#15803d" }}>Real</span>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
