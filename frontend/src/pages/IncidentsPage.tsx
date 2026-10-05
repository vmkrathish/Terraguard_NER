import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FieldReport } from "../types";
import LocationPicker from "../components/LocationPicker";
import RiskBadge from "../components/RiskBadge";
import StatusBadge from "../components/StatusBadge";

const INCIDENT_TYPES = ["crack", "slope_movement", "landslide", "blocked_road", "debris", "flooding", "other"];

export default function IncidentsPage() {
  const [reports, setReports] = useState<FieldReport[]>([]);
  const [form, setForm] = useState({
    latitude: "25.17", longitude: "93.02", incident_type: "crack", description: "", severity: "moderate", reporter_name: "",
  });
  const [otherIncidentType, setOtherIncidentType] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [recentOpen, setRecentOpen] = useState(false);

  const load = () => api.get<FieldReport[]>("/reports").then((r) => setReports(r.data));

  useEffect(() => { load(); }, []);

  const submit = async () => {
    const customIncidentType = otherIncidentType.trim();
    if (form.incident_type === "other" && !customIncidentType) {
      setMessage("Please specify the incident type.");
      return;
    }

    setSubmitting(true);
    setMessage(null);
    try {
      const data = new FormData();
      const description = form.incident_type === "other"
        ? `Other incident type: ${customIncidentType}${form.description ? `\n${form.description}` : ""}`
        : form.description;
      Object.entries({ ...form, description }).forEach(([k, v]) => data.append(k, v));
      if (photo) data.append("photo", photo);
      await api.post("/reports", data, { headers: { "Content-Type": "multipart/form-data" } });
      setMessage("Report submitted.");
      setForm({ ...form, description: "" });
      setOtherIncidentType("");
      setPhoto(null);
      load();
      setRecentOpen(true);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <h2 className="page-title">Field Incidents</h2>
      <p className="page-subtitle">Geotagged citizen/field reports with optional AI-assisted photo analysis.</p>

      <div className={`grid incident-workspace ${recentOpen ? "reports-ready" : "reports-pending"}`}>
        <div className="card">
          <h3>Submit a report</h3>
          <label>Location
            <LocationPicker
              latitude={form.latitude}
              longitude={form.longitude}
              onChange={(latitude, longitude) => setForm({ ...form, latitude, longitude })}
            />
          </label>
          <label>Incident type
            <select value={form.incident_type} onChange={(e) => setForm({ ...form, incident_type: e.target.value })}>
              {INCIDENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          {form.incident_type === "other" && (
            <label>Specify incident type
              <input
                value={otherIncidentType}
                onChange={(e) => setOtherIncidentType(e.target.value)}
                placeholder="e.g. sinkhole"
                required
              />
            </label>
          )}
          <label>Severity
            <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
              {["low", "moderate", "high", "critical", "unknown"].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Reporter name (optional)<input value={form.reporter_name} onChange={(e) => setForm({ ...form, reporter_name: e.target.value })} /></label>
          <label>Description<textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <label>Photo (optional)
            <input type="file" accept="image/*" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          </label>
          <button className="primary blue-action-button" onClick={submit} disabled={submitting}>{submitting ? "Submitting..." : "Submit report"}</button>
          {message && <p>{message}</p>}
        </div>

        {recentOpen && <div className="card incident-reports-card">
          <h3>Recent reports ({reports.length})</h3>
          {reports.length === 0 && <p className="table-empty">No field reports submitted yet.</p>}
          {reports.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Type</th><th>Severity</th><th>Sync</th><th>AI assessment</th></tr></thead>
                <tbody>
                  {reports.map((r) => (
                    <tr key={r.id}>
                      <td>{r.incident_type}</td>
                      <td><RiskBadge level={r.severity} /></td>
                      <td><StatusBadge status={r.sync_status} /></td>
                      <td>{r.photo_ai_analysis ? (r.photo_ai_analysis as { label?: string }).label ?? "n/a" : "no photo"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>}
      </div>
    </div>
  );
}
