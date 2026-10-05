import { Link } from "react-router-dom";

// Deterministic action links based only on risk_level — not an LLM
// recommendation engine. All actions are always present; only their visual
// emphasis/order changes by risk level.
export default function OperationalActions({
  riskLevel, latitude, longitude,
}: {
  riskLevel: string;
  latitude?: number;
  longitude?: number;
}) {
  const elevated = riskLevel === "HIGH" || riskLevel === "CRITICAL";
  const weatherTo = latitude != null && longitude != null
    ? `/weather?lat=${latitude}&lon=${longitude}`
    : "/weather";

  const actions = [
    { to: "/map", label: "View on GIS Map", emphasize: false },
    { to: weatherTo, label: "View live weather for this location", emphasize: false },
    { to: "/alerts", label: "Open Alert Intelligence Center", emphasize: elevated },
    { to: "/route", label: "Review Emergency Route", emphasize: elevated },
    { to: "/incidents", label: "Review field reports", emphasize: false },
  ];

  return (
    <div className="card">
      <span className="section-label">Operational actions</span>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
        {actions.map((a) => (
          <Link key={a.to} to={a.to} className={`btn ${a.emphasize ? "btn-primary" : "btn-ghost"}`}>
            {a.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
