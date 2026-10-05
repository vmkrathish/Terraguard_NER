import { useState } from "react";
import { api } from "../../api/client";
import type { Alert, AlertIssueRequest, ThreatEntry } from "../../types";
import LocationPicker from "../LocationPicker";

const THREAT_TYPES = [
  { value: "landslide_risk", label: "Landslide risk" },
  { value: "road_blockage", label: "Road blockage" },
  { value: "rainfall_shock", label: "Rainfall shock" },
  { value: "field_incident", label: "Field incident" },
];

const SEVERITIES = ["low", "moderate", "high", "critical"];

const RECIPIENT_CHANNELS = [
  { value: "authority@terraguard.demo", label: "Authority", simulation: false },
  { value: "field_officer@terraguard.demo", label: "Field Officers", simulation: false },
  { value: "community@terraguard.demo", label: "Community", simulation: true },
  { value: "emergency_team@terraguard.demo", label: "Emergency Services", simulation: true },
];

const ACTION_PRESETS = [
  "Evacuate low-lying areas immediately",
  "Avoid travel on affected roads until cleared",
  "Move to nearest designated safe zone",
  "Field officers to confirm ground conditions",
];

interface Props {
  prefillThreat: ThreatEntry | null;
  onClose: () => void;
  onIssued: (alert: Alert) => void;
}

// The real "issue a new warning" flow — POST /alerts/issue. Immediate-only
// (no scheduling), English-only (no multilingual support exists in this
// backend), and deliberately keeps recipients honest: Community/Emergency
// Services are simulation-only delivery channels, labeled as such.
export default function AlertComposer({ prefillThreat, onClose, onIssued }: Props) {
  const [recipients, setRecipients] = useState<string[]>(["authority@terraguard.demo", "field_officer@terraguard.demo"]);
  const [threatType, setThreatType] = useState("landslide_risk");
  const [severity, setSeverity] = useState(prefillThreat ? prefillThreat.risk_level.toLowerCase() : "high");
  const [lat, setLat] = useState(prefillThreat ? String(prefillThreat.latitude) : "25.17");
  const [lon, setLon] = useState(prefillThreat ? String(prefillThreat.longitude) : "93.02");
  const [state, setState] = useState(prefillThreat?.state || "");
  const [district, setDistrict] = useState(prefillThreat?.district || "");
  const [action, setAction] = useState(ACTION_PRESETS[0]);
  const [reason, setReason] = useState(prefillThreat ? `${prefillThreat.risk_level} risk threat at ${prefillThreat.name}` : "");
  const [showPreview, setShowPreview] = useState(false);
  const [issuing, setIssuing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issued, setIssued] = useState<Alert | null>(null);

  const toggleRecipient = (value: string) =>
    setRecipients((r) => (r.includes(value) ? r.filter((x) => x !== value) : [...r, value]));

  const payload: AlertIssueRequest = {
    recipients,
    threat_type: threatType,
    latitude: parseFloat(lat),
    longitude: parseFloat(lon),
    state: state || null,
    district: district || null,
    severity,
    action,
    risk_zone_id: prefillThreat?.risk_zone_id ?? null,
    reason: reason || "No reason provided",
  };

  const issue = async () => {
    setIssuing(true);
    setError(null);
    try {
      const { data } = await api.post<Alert>("/alerts/issue", payload);
      setIssued(data);
      onIssued(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to issue warning");
    } finally {
      setIssuing(false);
    }
  };

  return (
    <div className="ai-modal-backdrop" onClick={onClose}>
      <div className="ai-modal ai-modal-lg" onClick={(e) => e.stopPropagation()}>
        <div className="ai-modal-header">
          <h3 style={{ margin: 0 }}>Alert Composer — Issue Warning</h3>
          <button className="ai-modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="ai-modal-body">
          {issued ? (
            <div>
              <div className="form-alert success">
                Warning issued. Alert ID <strong>#{issued.id}</strong> was assigned by the server on issue.
              </div>
              <button className="btn btn-ghost" onClick={onClose}>Close</button>
            </div>
          ) : !showPreview ? (
            <>
              <h4 style={{ marginTop: 0 }}>Who — recipients</h4>
              <div className="chip-row" style={{ marginBottom: "var(--sp-4)" }}>
                {RECIPIENT_CHANNELS.map((c) => (
                  <label key={c.value} className={`chip-toggle ${recipients.includes(c.value) ? "on" : ""}`}>
                    <input type="checkbox" checked={recipients.includes(c.value)} onChange={() => toggleRecipient(c.value)} />
                    {c.label}
                    {c.simulation && <span className="sim-badge">SIMULATION</span>}
                  </label>
                ))}
              </div>

              <div className="grid grid-2">
                <label>
                  What — threat type
                  <select value={threatType} onChange={(e) => setThreatType(e.target.value)}>
                    {THREAT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </label>
                <label>
                  Severity
                  <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                    {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </label>
              </div>

              <h4>Where</h4>
              {prefillThreat ? (
                <p className="page-subtitle" style={{ marginBottom: "var(--sp-3)" }}>
                  Using the selected threat's location: <strong>{prefillThreat.name}</strong> ({prefillThreat.latitude}, {prefillThreat.longitude}).
                  You can still adjust it below.
                </p>
              ) : null}
              <LocationPicker latitude={lat} longitude={lon} onChange={(a, b) => { setLat(a); setLon(b); }} height={180} />
              <div className="grid grid-2">
                <label>State (optional)<input value={state} onChange={(e) => setState(e.target.value)} /></label>
                <label>District (optional)<input value={district} onChange={(e) => setDistrict(e.target.value)} /></label>
              </div>

              <h4>When</h4>
              <p className="page-subtitle" style={{ marginBottom: "var(--sp-3)" }}>Immediate only — this system does not support scheduled alerts.</p>

              <h4>Action</h4>
              <div className="chip-row" style={{ marginBottom: 8 }}>
                {ACTION_PRESETS.map((p) => (
                  <button key={p} type="button" className="btn btn-ghost" style={{ fontSize: 12.5 }} onClick={() => setAction(p)}>{p}</button>
                ))}
              </div>
              <label>Recommended action<textarea rows={2} value={action} onChange={(e) => setAction(e.target.value)} /></label>
              <label>Reason<textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></label>

              <p className="page-subtitle">Language: English only — this backend does not offer multilingual alert delivery.</p>

              <button className="primary" onClick={() => setShowPreview(true)} disabled={recipients.length === 0}>Preview Warning</button>
            </>
          ) : (
            <>
              <h4 style={{ marginTop: 0 }}>Preview — exactly what will be sent</h4>
              <div className="card" style={{ background: "var(--surface-2)" }}>
                <table>
                  <tbody>
                    <tr><td>Recipients</td><td>{recipients.join(", ")}</td></tr>
                    <tr><td>Threat type</td><td>{threatType}</td></tr>
                    <tr><td>Severity</td><td>{severity}</td></tr>
                    <tr><td>Location</td><td>{payload.latitude}, {payload.longitude}{state ? ` — ${state}` : ""}{district ? `, ${district}` : ""}</td></tr>
                    <tr><td>When</td><td>Immediate</td></tr>
                    <tr><td>Action</td><td>{action}</td></tr>
                    <tr><td>Reason</td><td>{reason}</td></tr>
                  </tbody>
                </table>
                <p className="page-subtitle" style={{ marginTop: 10, marginBottom: 0 }}>
                  An Alert ID will be assigned by the server once issued — not shown until then.
                </p>
              </div>
              {error && <div className="form-alert error">{error}</div>}
              <div style={{ display: "flex", gap: 8, marginTop: "var(--sp-4)" }}>
                <button className="btn btn-ghost" onClick={() => setShowPreview(false)} disabled={issuing}>Back to edit</button>
                <button className="primary" onClick={issue} disabled={issuing}>{issuing ? "Issuing..." : "Issue Warning"}</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
