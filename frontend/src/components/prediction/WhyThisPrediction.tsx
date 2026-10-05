import { useState } from "react";
import type { RiskPredictResponse } from "../../types";

// The existing SHAP / feature-importance-fallback contributing-factors bars,
// moved here verbatim from the old PredictionPage, plus an expandable
// "Technical details" toggle for the raw values. Honest about which
// explanation method actually produced the numbers.
export default function WhyThisPrediction({ result }: { result: RiskPredictResponse }) {
  const [showTechnical, setShowTechnical] = useState(false);

  if (result.explainability_method === "unavailable" || result.contributing_factors.length === 0) {
    return (
      <div className="card">
        <span className="section-label">Why this prediction</span>
        <p style={{ color: "var(--text-dim)", fontSize: 13 }}>No explainability output is available for this prediction.</p>
      </div>
    );
  }

  const methodLabel =
    result.explainability_method === "shap"
      ? "SHAP explanation"
      : result.explainability_method === "feature_importance_fallback"
      ? "Feature-importance fallback (SHAP unavailable)"
      : result.explainability_method;

  const maxAbsContribution = Math.max(...result.contributing_factors.map((f) => Math.abs(f.contribution)), 0.001);

  return (
    <div className="card">
      <span className="section-label">Why this prediction</span>
      <h4 style={{ marginTop: 6 }}>{methodLabel}</h4>
      {result.contributing_factors.map((f) => (
        <div key={f.feature} style={{ marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
            <span>{f.feature}</span>
            <span style={{ color: f.direction === "increases_risk" ? "var(--critical)" : "var(--low)", fontWeight: 700 }}>
              {f.direction === "increases_risk" ? "▲ increases risk" : "▼ decreases risk"} · {f.contribution.toFixed(3)}
            </span>
          </div>
          <div className="factor-bar">
            <div style={{
              width: `${(Math.abs(f.contribution) / maxAbsContribution) * 100}%`,
              background: f.direction === "increases_risk" ? "var(--critical)" : "var(--low)",
            }} />
          </div>
        </div>
      ))}

      <button type="button" className="btn btn-ghost" style={{ marginTop: 6, fontSize: 12, padding: "5px 10px" }} onClick={() => setShowTechnical((v) => !v)}>
        {showTechnical ? "Hide technical details" : "Show technical details"}
      </button>

      {showTechnical && (
        <div className="table-scroll" style={{ marginTop: 10 }}>
          <table>
            <thead><tr><th>Feature</th><th>Contribution (raw)</th><th>Direction</th></tr></thead>
            <tbody>
              {result.contributing_factors.map((f) => (
                <tr key={f.feature}>
                  <td>{f.feature}</td>
                  <td>{f.contribution}</td>
                  <td>{f.direction}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 6 }}>
            Explainability method (raw): <code>{result.explainability_method}</code>
          </p>
        </div>
      )}

      {Object.keys(result.rainfall_context).length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4>Geographic &amp; rainfall context</h4>
          <table>
            <tbody>
              {Object.entries(result.rainfall_context).map(([k, v]) => (
                <tr key={k}>
                  <td style={{ color: "var(--text-dim)" }}>{k.replace(/_/g, " ")}</td>
                  <td>{v === null || v === undefined ? "–" : String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ marginTop: 16, fontSize: 12, color: "var(--text-dim)" }}>{result.disclaimer}</p>
    </div>
  );
}
