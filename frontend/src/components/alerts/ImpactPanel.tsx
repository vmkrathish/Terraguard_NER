import type { ImpactAssessment } from "../../types";

// Renders a real ImpactAssessment (or a /alerts/simulate scenario result,
// which has the same shape plus scenario/scenario_description set). Never
// treats a null population as 0, always surfaces population_note verbatim.
export default function ImpactPanel({ impact }: { impact: ImpactAssessment }) {
  return (
    <div className="impact-panel">
      {impact.scenario && (
        <div className="form-alert" style={{ background: "var(--gold-soft)", borderColor: "rgba(181,140,43,0.35)", color: "var(--text)" }}>
          <strong style={{ marginRight: 6 }}>SIMULATION / SCENARIO</strong>
          {impact.scenario_description || "Hypothetical what-if scenario — not a real prediction."}
        </div>
      )}

      <div className="grid grid-2" style={{ marginBottom: "var(--sp-3)" }}>
        <div className="impact-stat">
          <div className="impact-stat-value">
            {impact.total_population_known == null ? "Unknown" : impact.total_population_known.toLocaleString()}
          </div>
          <div className="impact-stat-label">People in impact area (known)</div>
          {impact.population_note && <div className="impact-stat-note">{impact.population_note}</div>}
        </div>
        <div className="impact-stat" id="impact-safezone">
          <div className="impact-stat-value">
            {impact.safe_zone ? `${impact.safe_zone.distance_km.toFixed(1)} km` : "No safe zone found"}
          </div>
          <div className="impact-stat-label">Nearest safe zone{impact.safe_zone ? ` — ${impact.safe_zone.name}` : ""}</div>
          {impact.safe_zone?.inside_risk_zone && (
            <div className="impact-stat-note" style={{ color: "var(--critical)" }}>Warning: candidate safe zone itself falls inside a risk zone.</div>
          )}
        </div>
      </div>

      <div className="grid grid-4">
        <div id="impact-list-villages"><ImpactList title="Villages" items={impact.affected_villages.map((v) => `${v.name} — pop. ${v.population == null ? "unknown" : v.population.toLocaleString()} (${Math.round(v.distance_m)}m)`)} /></div>
        <div id="impact-list-roads"><ImpactList title="Roads" items={impact.affected_roads.map((r) => `${r.name} — ${r.status} (${Math.round(r.distance_m)}m)`)} /></div>
        <div id="impact-list-facilities"><ImpactList title="Hospitals" items={impact.affected_hospitals.map((h) => `${h.name} (${Math.round(h.distance_m)}m)`)} /></div>
        <div><ImpactList title="Schools" items={impact.affected_schools.map((s) => `${s.name} (${Math.round(s.distance_m)}m)`)} /></div>
      </div>

      {impact.safe_zone?.route_if_road_blocked && (
        <div className="card" style={{ marginTop: "var(--sp-3)", background: "var(--surface-2)" }}>
          <h4 style={{ margin: "0 0 6px" }}>Route if road blocked (scenario)</h4>
          <p style={{ margin: 0, fontSize: "var(--fs-sm)" }}>
            {impact.safe_zone.route_if_road_blocked.label} — {impact.safe_zone.route_if_road_blocked.distance_km.toFixed(1)} km,
            {" "}{impact.safe_zone.route_if_road_blocked.avoided_segments} segment(s) avoided.
          </p>
        </div>
      )}
    </div>
  );
}

function ImpactList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="impact-list-card">
      <div className="impact-list-title">{title} ({items.length})</div>
      {items.length === 0 ? (
        <p className="table-empty" style={{ margin: 0 }}>None within range</p>
      ) : (
        <ul className="impact-list">
          {items.map((it, i) => <li key={i}>{it}</li>)}
        </ul>
      )}
    </div>
  );
}
