import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Evidence } from "../../types";
import EvidenceChain from "../alerts/EvidenceChain";

// Fetches GET /alerts/evidence for the current location/state/district and
// renders it with the existing EvidenceChain component.
export default function EvidenceSection({
  latitude,
  longitude,
  state,
  district,
}: {
  latitude: number;
  longitude: number;
  state: string;
  district: string;
}) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get<Evidence>("/alerts/evidence", { params: { lat: latitude, lon: longitude, state: state || undefined, district: district || undefined } })
      .then((resp) => !cancelled && setEvidence(resp.data))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Failed to load evidence"))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [latitude, longitude, state, district]);

  return (
    <div className="card">
      <span className="section-label">Evidence</span>
      {loading && <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 8 }}>Loading evidence...</p>}
      {error && <div className="form-alert error">{error}</div>}
      {!loading && evidence && <EvidenceChain evidence={evidence} />}
    </div>
  );
}
