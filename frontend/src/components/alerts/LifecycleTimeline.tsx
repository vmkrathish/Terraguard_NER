import { useState } from "react";
import { api } from "../../api/client";
import type { LifecycleStageEntry } from "../../types";
import { LIFECYCLE_STAGES } from "../../types";

const STAGE_LABELS: Record<string, string> = {
  detected: "Detected",
  assessed: "Assessed",
  impact_mapped: "Impact mapped",
  assigned: "Assigned",
  warning_issued: "Warning issued",
  acknowledged: "Acknowledged",
  action_started: "Action started",
  resolved: "Resolved",
};

// Stages the operator can manually record from this UI (the rest — detected,
// warning_issued, assigned, acknowledged — are set automatically by the
// backend when the corresponding real action happens: issuing the alert,
// making the first assignment, recording the first acknowledgement).
const MANUAL_STAGES = ["assessed", "impact_mapped", "action_started", "resolved"] as const;

interface Props {
  alertId: number;
  lifecycle: LifecycleStageEntry[];
  evidenceViewed: boolean;
  impactViewed: boolean;
  assignedThisSession: boolean;
  onChanged: () => void;
}

// Renders the real 8-stage array from GET /alerts/{id}/lifecycle — done (with
// its real timestamp) or pending, never backfilled. Manual "mark done"
// buttons are gated on real UI actions actually having happened this
// session, per the product spec's honesty requirement (e.g. impact_mapped
// only enables after the Impact panel has actually been opened for this alert).
export default function LifecycleTimeline({ alertId, lifecycle, evidenceViewed, impactViewed, assignedThisSession, onChanged }: Props) {
  const [busyStage, setBusyStage] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const byStage = new Map(lifecycle.map((l) => [l.stage, l]));
  const actionStartedDone = byStage.get("action_started")?.status === "done";

  const gateFor = (stage: string): { enabled: boolean; reason: string } => {
    if (stage === "assessed") return { enabled: evidenceViewed, reason: "Open the Evidence panel for this alert first." };
    if (stage === "impact_mapped") return { enabled: impactViewed, reason: "Open the Impact panel for this alert first." };
    if (stage === "action_started") return { enabled: assignedThisSession, reason: "Assign a response first." };
    if (stage === "resolved") return { enabled: actionStartedDone, reason: "Mark action started first." };
    return { enabled: true, reason: "" };
  };

  const markStage = async (stage: string) => {
    setBusyStage(stage);
    setError(null);
    try {
      await api.post(`/alerts/${alertId}/lifecycle`, { stage, note: note || undefined });
      setNote("");
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to record stage ${stage}`);
    } finally {
      setBusyStage(null);
    }
  };

  return (
    <div>
      <ol className="lifecycle-timeline">
        {LIFECYCLE_STAGES.map((stage) => {
          const entry = byStage.get(stage);
          const done = entry?.status === "done";
          const manual = (MANUAL_STAGES as readonly string[]).includes(stage);
          const gate = manual ? gateFor(stage) : { enabled: false, reason: "" };
          return (
            <li key={stage} className={`lifecycle-stage ${done ? "done" : "pending"}`}>
              <span className="lifecycle-stage-dot" aria-hidden="true">{done ? "✓" : "○"}</span>
              <div className="lifecycle-stage-body">
                <div className="lifecycle-stage-name">{STAGE_LABELS[stage] ?? stage}</div>
                <div className="lifecycle-stage-meta">
                  {done ? (entry?.occurred_at ? new Date(entry.occurred_at).toLocaleString() : "done") : "pending"}
                  {entry?.note && ` — ${entry.note}`}
                </div>
                {manual && !done && (
                  <button
                    className="btn btn-ghost"
                    style={{ marginTop: 6, fontSize: 12 }}
                    disabled={!gate.enabled || busyStage === stage}
                    title={!gate.enabled ? gate.reason : undefined}
                    onClick={() => markStage(stage)}
                  >
                    {busyStage === stage ? "Recording..." : `Mark ${STAGE_LABELS[stage]}`}
                  </button>
                )}
                {manual && !done && !gate.enabled && <div className="impact-stat-note">{gate.reason}</div>}
              </div>
            </li>
          );
        })}
      </ol>
      <label style={{ marginTop: "var(--sp-3)" }}>
        Optional note for the next stage you record
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. field-confirmed, escalating response" />
      </label>
      {error && <div className="form-alert error">{error}</div>}
    </div>
  );
}
