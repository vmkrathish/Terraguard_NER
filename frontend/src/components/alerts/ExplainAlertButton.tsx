import { useState } from "react";
import { api } from "../../api/client";
import type { AlertDetail, RagQueryResponse } from "../../types";

// A plain-language explanation layer over data already fetched for this
// alert — never a new data source. The question sent to /rag/query is built
// only from this alert's own real evidence/impact values; the RAG pipeline
// is asked to explain, never to invent a risk score, population or location.
export default function ExplainAlertButton({ detail }: { detail: AlertDetail }) {
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<RagQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const explain = async () => {
    setLoading(true);
    setError(null);
    setAnswer(null);
    const { alert, evidence, impact } = detail;
    const verifiedSignals = evidence.signals.filter((s) => s.verified).map((s) => s.label).join(", ") || "none verified yet";
    const location = [alert.district, alert.state].filter(Boolean).join(", ") || `${alert.latitude}, ${alert.longitude}`;
    const question =
      `Explain the evidence and impact for the ${alert.severity} threat at ${location}: ` +
      `verified signals are ${verifiedSignals}. Affected entities are ${impact.affected_villages.length} villages, ` +
      `${impact.affected_roads.length} roads, ${impact.affected_hospitals.length} hospitals and ${impact.affected_schools.length} schools.`;
    try {
      const { data } = await api.post<RagQueryResponse>("/rag/query", { question, top_k: 5 });
      setAnswer(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to get an explanation");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button className="btn btn-ghost" onClick={explain} disabled={loading}>
        {loading ? "Explaining..." : "Explain This Alert"}
      </button>
      {error && <div className="form-alert error" style={{ marginTop: 8 }}>{error}</div>}
      {answer && (
        <div className="card" style={{ marginTop: 8, background: "var(--surface-2)" }}>
          {answer.answer_type === "insufficient_data" ? (
            <p style={{ margin: 0 }}>Not enough information is available to explain this alert further.</p>
          ) : (
            <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{answer.answer}</p>
          )}
        </div>
      )}
    </div>
  );
}
