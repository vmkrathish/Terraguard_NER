import type { AlertDetail } from "../../types";

interface Node {
  key: string;
  label: string;
  detail: string;
  scrollTo?: string;
}

// A compact relationship chain built only from data already fetched for this
// alert (evidence/impact/lifecycle) — not a fake 3D visualization. Clicking a
// node scrolls to/highlights the matching section already rendered elsewhere
// on the War Room page.
export default function DigitalTwinView({ detail }: { detail: AlertDetail }) {
  const { alert, evidence, impact, lifecycle } = detail;
  const responseStage = lifecycle.find((l) => l.stage === "action_started" && l.status === "done")
    ? "Action started"
    : lifecycle.find((l) => l.stage === "assigned" && l.status === "done")
    ? "Assigned"
    : "Not yet assigned";

  const nodes: Node[] = [
    { key: "threat", label: "Threat", detail: `${alert.severity.toUpperCase()} — ${alert.alert_type}` },
    { key: "risk", label: "Risk / Evidence", detail: `${evidence.verified_count}/${evidence.total_count} signals` },
    { key: "villages", label: "Villages", detail: `${impact.affected_villages.length}`, scrollTo: "impact-list-villages" },
    { key: "roads", label: "Roads", detail: `${impact.affected_roads.length}`, scrollTo: "impact-list-roads" },
    { key: "facilities", label: "Facilities", detail: `${impact.affected_hospitals.length + impact.affected_schools.length}`, scrollTo: "impact-list-facilities" },
    { key: "safe_route", label: "Safe route", detail: impact.safe_zone ? `${impact.safe_zone.distance_km.toFixed(1)} km` : "None found", scrollTo: "impact-safezone" },
    { key: "response", label: "Response", detail: responseStage },
  ];

  const goTo = (id?: string) => {
    if (!id) return;
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("twin-highlight");
      setTimeout(() => el.classList.remove("twin-highlight"), 1200);
    }
  };

  return (
    <div className="digital-twin-chain">
      {nodes.map((n, i) => (
        <div key={n.key} style={{ display: "contents" }}>
          <button type="button" className="digital-twin-node" onClick={() => goTo(n.scrollTo)} disabled={!n.scrollTo}>
            <div className="digital-twin-node-label">{n.label}</div>
            <div className="digital-twin-node-detail">{n.detail}</div>
          </button>
          {i < nodes.length - 1 && <span className="digital-twin-arrow" aria-hidden="true">→</span>}
        </div>
      ))}
    </div>
  );
}
