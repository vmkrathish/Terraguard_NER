import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { ImpactAssessment, RiskPredictResponse } from "../../types";
import ImpactPanel from "../alerts/ImpactPanel";

// Fetches the broader-radius GET /alerts/impact-assessment and renders it
// with the existing ImpactPanel component, while keeping the prediction's
// own point-specific chain_reaction_impact fields (isolated villages,
// emergency accessibility, nearest hospital) visible alongside — that data
// is real and specific to the exact predicted point, complementing rather
// than duplicating the radius-based assessment.
export default function ImpactSection({ result, latitude, longitude }: { result: RiskPredictResponse; latitude: number; longitude: number }) {
  const [impact, setImpact] = useState<ImpactAssessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get<ImpactAssessment>("/alerts/impact-assessment", { params: { lat: latitude, lon: longitude, radius_m: 20000 } })
      .then((resp) => !cancelled && setImpact(resp.data))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Failed to load impact assessment"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [latitude, longitude]);

  const chain = result.chain_reaction_impact;

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <span className="section-label">Impact assessment (20km radius)</span>
        <Link to="/map" className="btn btn-ghost" style={{ fontSize: 12, padding: "5px 10px" }}>View on GIS Map</Link>
      </div>

      {chain && (
        <div style={{ marginTop: 10, marginBottom: 14, padding: "10px 12px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)", fontSize: 13 }}>
          <p style={{ margin: "0 0 4px" }}>Emergency accessibility at this point: <b>{chain.emergency_accessibility}</b></p>
          {chain.isolated_villages.length > 0 && (
            <p style={{ color: "var(--critical)", fontWeight: 600, margin: "0 0 4px" }}>
              ⚠ Isolated villages: {chain.isolated_villages.map((v) => v.name).join(", ")}
            </p>
          )}
          {chain.nearest_hospital && (
            <p style={{ margin: 0 }}>Nearest hospital: {chain.nearest_hospital.name} ({chain.nearest_hospital_distance_km} km)</p>
          )}
        </div>
      )}

      {loading && <p style={{ color: "var(--text-dim)", fontSize: 13 }}>Loading impact assessment...</p>}
      {error && <div className="form-alert error">{error}</div>}
      {!loading && impact && <ImpactPanel impact={impact} />}
    </div>
  );
}
