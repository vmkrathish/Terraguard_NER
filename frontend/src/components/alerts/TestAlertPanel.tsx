import { useState } from "react";
import { api } from "../../api/client";
import LocationPicker from "../LocationPicker";

interface Props {
  onSent: () => void;
}

// The original test/dev alert action (POST /alerts/test), kept reachable and
// visually separated from the real Alert Composer (POST /alerts/issue) — the
// backend keeps these as two different endpoints deliberately.
export default function TestAlertPanel({ onSent }: Props) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ alert_type: "test", severity: "high", latitude: "25.17", longitude: "93.02", reason: "" });
  const [sending, setSending] = useState(false);

  const sendTest = async () => {
    setSending(true);
    try {
      await api.post("/alerts/test", {
        alert_type: form.alert_type,
        severity: form.severity,
        latitude: parseFloat(form.latitude),
        longitude: parseFloat(form.longitude),
        reason: form.reason || "Test alert triggered from the Alert Intelligence Center",
      });
      onSent();
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="card test-alert-panel">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h3 style={{ margin: 0 }}>Testing / dev tools</h3>
          <p className="page-subtitle" style={{ margin: "2px 0 0" }}>
            Send a test alert without going through the real issue workflow — for verifying delivery plumbing only.
          </p>
        </div>
        <button className="btn btn-ghost" onClick={() => setOpen((o) => !o)}>{open ? "Hide" : "Open"}</button>
      </div>

      {open && (
        <div style={{ marginTop: "var(--sp-4)" }}>
          <span className="sim-badge" style={{ marginBottom: 10, display: "inline-block" }}>TEST / DEV ONLY</span>
          <div className="grid grid-2">
            <label>Alert type
              <select value={form.alert_type} onChange={(e) => setForm({ ...form, alert_type: e.target.value })}>
                {["test", "risk_escalation", "high_critical_risk", "severe_incident", "road_blockage", "rainfall_shock"].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label>Severity
              <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
                {["low", "moderate", "high", "critical"].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
          </div>
          <label>Location
            <LocationPicker
              latitude={form.latitude}
              longitude={form.longitude}
              onChange={(latitude, longitude) => setForm({ ...form, latitude, longitude })}
              height={180}
            />
          </label>
          <label>Reason<textarea rows={2} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></label>
          <button className="btn btn-ghost" onClick={sendTest} disabled={sending}>{sending ? "Sending..." : "Send test alert"}</button>
        </div>
      )}
    </div>
  );
}
