import { useEffect, useState } from "react";
import { Circle, MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import "../../leafletSetup";
import { api } from "../../api/client";
import type { AlertDetail, UserSummary } from "../../types";
import RiskBadge from "../RiskBadge";
import EvidenceChain from "./EvidenceChain";
import ImpactPanel from "./ImpactPanel";
import LifecycleTimeline from "./LifecycleTimeline";
import AcknowledgementPanel from "./AcknowledgementPanel";
import DigitalTwinView from "./DigitalTwinView";
import ExplainAlertButton from "./ExplainAlertButton";

type Tab = "overview" | "evidence" | "impact" | "twin" | "timeline";

interface Props {
  alertId: number;
  currentUserRole: string | undefined;
  onClose: () => void;
  onOpenSimulator: (title: string, lat: number, lon: number, radiusM: number) => void;
}

// Incident War Room — the single-source-of-truth view for one already-issued
// alert, backed entirely by GET /alerts/{id}. Only actions the backend
// actually supports are offered (assign, lifecycle stage bumps, resolve) —
// no invented "escalate" API, just a lifecycle POST with a note.
export default function WarRoom({ alertId, currentUserRole, onClose, onOpenSimulator }: Props) {
  const [detail, setDetail] = useState<AlertDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [evidenceViewed, setEvidenceViewed] = useState(false);
  const [impactViewed, setImpactViewed] = useState(false);
  const [assignedThisSession, setAssignedThisSession] = useState(false);

  // Assign Response now picks a real, registered account (GET /auth/users)
  // instead of accepting a free-typed name — the role is never chosen
  // manually, it's read straight off that account so the two can never
  // mismatch (e.g. typing "Priya" but picking "authority" when Priya is
  // actually a field officer).
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [assigning, setAssigning] = useState(false);
  const selectedUser = users.find((u) => String(u.id) === selectedUserId) || null;

  const [escalateStage, setEscalateStage] = useState("action_started");
  const [escalateNote, setEscalateNote] = useState("");
  const [escalating, setEscalating] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .get<AlertDetail>(`/alerts/${alertId}`)
      .then((r) => setDetail(r.data))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load this incident"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertId]);

  useEffect(() => {
    api
      .get<UserSummary[]>("/auth/users")
      .then((r) => setUsers(r.data))
      .catch((e) => setUsersError(e instanceof Error ? e.message : "Failed to load the list of registered accounts"));
  }, []);

  const changeTab = (t: Tab) => {
    setTab(t);
    if (t === "evidence") setEvidenceViewed(true);
    if (t === "impact") setImpactViewed(true);
  };

  const assign = async () => {
    if (!selectedUser) return;
    setAssigning(true);
    try {
      await api.post(`/alerts/${alertId}/assign`, { assignee_name: selectedUser.full_name, role: selectedUser.role });
      setAssignedThisSession(true);
      setSelectedUserId("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to assign response");
    } finally {
      setAssigning(false);
    }
  };

  const escalate = async () => {
    if (!escalateNote.trim()) return;
    setEscalating(true);
    try {
      await api.post(`/alerts/${alertId}/lifecycle`, { stage: escalateStage, note: escalateNote });
      setEscalateNote("");
      if (escalateStage === "action_started") setAssignedThisSession((v) => v || true);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to escalate");
    } finally {
      setEscalating(false);
    }
  };

  if (loading && !detail) return <div className="card"><p className="table-empty">Loading incident...</p></div>;
  if (error && !detail) return <div className="card"><div className="form-alert error">{error}</div></div>;
  if (!detail) return null;

  const { alert, evidence, impact, lifecycle, acknowledgements } = detail;
  const hasLocation = alert.latitude != null && alert.longitude != null;

  return (
    <div className="card war-room">
      <div className="war-room-header">
        <div>
          <button className="btn btn-ghost" onClick={onClose} style={{ marginBottom: 8 }}>← Back to threat board</button>
          <h3 style={{ margin: 0 }}>War Room — Alert #{alert.id}</h3>
          <div className="threat-card-loc">{[alert.district, alert.state].filter(Boolean).join(", ") || "Location unknown"}</div>
        </div>
        <RiskBadge level={alert.severity} />
      </div>

      <div className="chip-row" style={{ marginBottom: "var(--sp-4)" }}>
        {(["overview", "evidence", "impact", "twin", "timeline"] as Tab[]).map((t) => (
          <button key={t} className={`chip-toggle ${tab === t ? "on" : ""}`} onClick={() => changeTab(t)} type="button">
            {t === "twin" ? "Digital Twin" : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {error && <div className="form-alert error">{error}</div>}

      {tab === "overview" && (
        <div className="grid grid-2">
          {hasLocation && (
            <div className="map-container" style={{ height: "38vh" }}>
              <MapContainer center={[alert.latitude!, alert.longitude!]} zoom={11} style={{ height: "100%", width: "100%" }}>
                <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                <Circle center={[alert.latitude!, alert.longitude!]} radius={20000} pathOptions={{ color: "#b3342f", fillOpacity: 0.1 }} />
                <Marker position={[alert.latitude!, alert.longitude!]}><Popup>{alert.reason}</Popup></Marker>
                {impact.safe_zone && (
                  <Marker position={[impact.safe_zone.latitude, impact.safe_zone.longitude]}>
                    <Popup>Safe zone: {impact.safe_zone.name}</Popup>
                  </Marker>
                )}
              </MapContainer>
            </div>
          )}
          <div>
            <h4 style={{ marginTop: 0 }}>Threat intelligence</h4>
            <table>
              <tbody>
                <tr><td>Severity</td><td><RiskBadge level={alert.severity} /></td></tr>
                <tr><td>Evidence</td><td>{evidence.verified_count}/{evidence.total_count} signals available</td></tr>
                <tr><td>Impact</td><td>{impact.affected_villages.length} villages, {impact.affected_roads.length} roads, {impact.affected_hospitals.length + impact.affected_schools.length} facilities</td></tr>
                <tr><td>Safe route</td><td>{impact.safe_zone ? `${impact.safe_zone.distance_km.toFixed(1)} km to ${impact.safe_zone.name}` : "None found"}</td></tr>
                <tr><td>Recommended action</td><td>{alert.recommended_action || "Not specified"}</td></tr>
              </tbody>
            </table>
            <div style={{ marginTop: "var(--sp-3)" }}><ExplainAlertButton detail={detail} /></div>
          </div>
        </div>
      )}

      {tab === "evidence" && <EvidenceChain evidence={evidence} />}
      {tab === "impact" && (
        <div>
          <ImpactPanel impact={impact} />
          <button className="btn btn-ghost" style={{ marginTop: 8 }} onClick={() => onOpenSimulator(`Alert #${alert.id}`, alert.latitude!, alert.longitude!, 20000)} disabled={!hasLocation}>
            Simulate Impact
          </button>
        </div>
      )}
      {tab === "twin" && <DigitalTwinView detail={detail} />}
      {tab === "timeline" && (
        <LifecycleTimeline
          alertId={alert.id}
          lifecycle={lifecycle}
          evidenceViewed={evidenceViewed}
          impactViewed={impactViewed}
          assignedThisSession={assignedThisSession}
          onChanged={load}
        />
      )}

      <div className="grid grid-2" style={{ marginTop: "var(--sp-5)" }}>
        <div className="card" style={{ background: "var(--surface-2)" }}>
          <h4 style={{ marginTop: 0 }}>Assign response</h4>
          <p className="page-subtitle" style={{ margin: "0 0 8px" }}>
            Pick a registered person — their role is read from their account, not typed, so it can never be assigned wrong.
          </p>
          {usersError && <div className="form-alert error">{usersError}</div>}
          <label>
            Assignee
            <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
              <option value="">Select a person...</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>
              ))}
            </select>
          </label>
          <label>
            Role (verified from account)
            <input value={selectedUser ? selectedUser.role : ""} readOnly disabled placeholder="Select a person above" />
          </label>
          <button className="btn btn-primary" onClick={assign} disabled={assigning || !selectedUser}>
            {assigning ? "Assigning..." : "Assign Response"}
          </button>
        </div>

        <div className="card" style={{ background: "var(--surface-2)" }}>
          <h4 style={{ marginTop: 0 }}>Escalate</h4>
          <p className="page-subtitle" style={{ margin: "0 0 8px" }}>
            Records a lifecycle stage with a note — there is no separate escalate API, this is the real lifecycle endpoint.
          </p>
          <label>
            Stage
            <select value={escalateStage} onChange={(e) => setEscalateStage(e.target.value)}>
              {["action_started", "resolved"].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Note (required)<input value={escalateNote} onChange={(e) => setEscalateNote(e.target.value)} placeholder="e.g. escalating to district authority" /></label>
          <button className="btn btn-ghost" onClick={escalate} disabled={escalating || !escalateNote.trim()}>
            {escalating ? "Recording..." : "Escalate"}
          </button>
        </div>
      </div>

      <div className="card" style={{ marginTop: "var(--sp-4)" }}>
        <h4 style={{ marginTop: 0 }}>Acknowledgements</h4>
        <AcknowledgementPanel alertId={alert.id} acknowledgements={acknowledgements} currentUserRole={currentUserRole} onChanged={load} />
      </div>
    </div>
  );
}
