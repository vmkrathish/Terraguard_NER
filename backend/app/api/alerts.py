from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.excel_store import Store, clean_records, clean_value, get_store
from app.services import alert_intelligence as ai
from app.services.alerting import create_alert
from app.api.deps import require_user
from app.schemas.schemas import (
    AcknowledgeRequest,
    AcknowledgementChannelStatus,
    AlertAssignmentOut,
    AlertDetailOut,
    AlertIssueRequest,
    AlertOut,
    AlertTestRequest,
    AssignRequest,
    EvidenceOut,
    ImpactAssessmentOut,
    LifecycleStageOut,
    LifecycleStageRequest,
    SimulateScenarioRequest,
    ThreatBoardEntry,
)

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(limit: int = 50, store: Store = Depends(get_store)):
    df = store.df("alerts").sort_values("created_at", ascending=False, na_position="last").head(limit)
    return clean_records(df.to_dict("records"))


@router.post("/alerts/test", response_model=AlertOut)
def test_alert(payload: AlertTestRequest, store: Store = Depends(get_store)):
    """Alert-history/testing interface: lets the system be demonstrated
    end-to-end without production FCM credentials. Distinct from the real
    Alert Composer at POST /alerts/issue — this path stays untouched."""
    alert = create_alert(
        store,
        alert_type=payload.alert_type,
        severity=payload.severity,
        reason=payload.reason,
        latitude=payload.latitude,
        longitude=payload.longitude,
        recommended_action="This is a test alert; no action required.",
    )
    return alert


# --------------------------------------------------------------------- #
# Alert Intelligence Center
# --------------------------------------------------------------------- #
def _latest_alert_for_zone(store: Store, risk_zone_id: int) -> Optional[dict]:
    alerts = store.df("alerts")
    if alerts.empty or "risk_zone_id" not in alerts.columns:
        return None
    matches = alerts[alerts["risk_zone_id"] == risk_zone_id]
    if matches.empty:
        return None
    matches = matches.sort_values("created_at", ascending=False)
    return clean_records(matches.head(1).to_dict("records"))[0]


@router.get("/alerts/threats", response_model=list[ThreatBoardEntry])
def threat_board(store: Store = Depends(get_store)):
    """Live Threat Board data source: every HIGH/CRITICAL risk_zones row,
    each with its live-computed evidence and a trimmed impact summary."""
    zones = store.df("risk_zones")
    if zones.empty:
        return []
    threats = zones[zones["risk_level"].astype(str).str.lower().isin(["high", "critical"])]

    out = []
    for _, z in threats.iterrows():
        evidence = ai.compute_evidence(
            store, z["latitude"], z["longitude"], state=clean_value(z.get("state")),
            district=clean_value(z.get("district")),
        )
        impact = ai.compute_impact(store, z["latitude"], z["longitude"], float(z["radius_m"]) if clean_value(z.get("radius_m")) else 20000)
        out.append({
            "risk_zone_id": int(z["id"]),
            "name": z["name"],
            "state": clean_value(z.get("state")),
            "district": clean_value(z.get("district")),
            "latitude": z["latitude"],
            "longitude": z["longitude"],
            "risk_level": z["risk_level"],
            "risk_score": clean_value(z.get("risk_score")),
            "evidence": evidence,
            "impact_summary": ai.impact_summary_counts(impact),
            "latest_alert": _latest_alert_for_zone(store, int(z["id"])),
        })
    return out


@router.get("/alerts/evidence", response_model=EvidenceOut)
def evidence(
    lat: float, lon: float, state: Optional[str] = None, district: Optional[str] = None,
    radius_m: float = 20000, store: Store = Depends(get_store),
):
    return ai.compute_evidence(store, lat, lon, state=state, district=district, radius_m=radius_m)


@router.get("/alerts/impact-assessment", response_model=ImpactAssessmentOut)
def impact_assessment(lat: float, lon: float, radius_m: float = 20000, store: Store = Depends(get_store)):
    return ai.compute_impact(store, lat, lon, radius_m)


@router.post("/alerts/simulate", response_model=ImpactAssessmentOut)
def simulate(payload: SimulateScenarioRequest, store: Store = Depends(get_store)):
    """Pure read-computation what-if scenario — never mutates the real
    `roads`/`risk_zones` tables."""
    return ai.simulate_scenario(
        store, payload.lat, payload.lon, payload.radius_m,
        radius_multiplier=payload.radius_multiplier, blocked_road_id=payload.blocked_road_id,
    )


def _get_alert_or_404(store: Store, alert_id: int) -> dict:
    alerts = store.df("alerts")
    match = alerts[alerts["id"] == alert_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"No alert with id {alert_id}.")
    return clean_records(match.head(1).to_dict("records"))[0]


@router.get("/alerts/{alert_id}", response_model=AlertDetailOut)
def alert_detail(alert_id: int, store: Store = Depends(get_store)):
    """War Room's single data source: the alert row + live-recomputed
    evidence/impact + lifecycle timeline + acknowledgement status."""
    alert = _get_alert_or_404(store, alert_id)
    lat, lon = alert.get("latitude"), alert.get("longitude")
    if lat is None or lon is None:
        raise HTTPException(status_code=422, detail="This alert has no latitude/longitude; evidence/impact cannot be computed.")

    evidence_out = ai.compute_evidence(store, lat, lon, state=alert.get("state"), district=alert.get("district"))
    impact_out = ai.compute_impact(store, lat, lon, 20000)
    lifecycle = ai.get_lifecycle_timeline(store, alert_id)
    acks = ai.get_acknowledgement_status(store, alert_id)

    return {
        "alert": alert,
        "evidence": evidence_out,
        "impact": impact_out,
        "lifecycle": lifecycle,
        "acknowledgements": acks,
    }


@router.get("/alerts/{alert_id}/lifecycle", response_model=list[LifecycleStageOut])
def lifecycle(alert_id: int, store: Store = Depends(get_store)):
    _get_alert_or_404(store, alert_id)
    return ai.get_lifecycle_timeline(store, alert_id)


@router.post("/alerts/{alert_id}/lifecycle", response_model=LifecycleStageOut)
def record_lifecycle(
    alert_id: int, payload: LifecycleStageRequest,
    store: Store = Depends(get_store), user: dict = Depends(require_user),
):
    _get_alert_or_404(store, alert_id)
    try:
        ai.record_lifecycle_stage(store, alert_id, payload.stage, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    matching = [s for s in ai.get_lifecycle_timeline(store, alert_id) if s["stage"] == payload.stage]
    return matching[0]


@router.post("/alerts/{alert_id}/acknowledge", response_model=dict[str, AcknowledgementChannelStatus])
def acknowledge(
    alert_id: int, payload: AcknowledgeRequest,
    store: Store = Depends(get_store), user: dict = Depends(require_user),
):
    _get_alert_or_404(store, alert_id)
    user_role = user.get("role")
    role = payload.role or user_role

    # An explicit role override is only allowed for the two simulation
    # channels — no real account exists for "community"/"emergency_team",
    # so there is nothing else that could supply that role honestly.
    if payload.role and payload.role != user_role and payload.role not in ai.SIMULATION_ACK_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only the simulation channels ('community', 'emergency_team') may be acknowledged on behalf of "
                   "someone else; real roles must acknowledge as the authenticated user.",
        )
    try:
        ai.record_acknowledgement(store, alert_id, role, acknowledged_by=user.get("full_name"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ai.get_acknowledgement_status(store, alert_id)


@router.get("/alerts/{alert_id}/acknowledgements", response_model=dict[str, AcknowledgementChannelStatus])
def acknowledgements(alert_id: int, store: Store = Depends(get_store)):
    _get_alert_or_404(store, alert_id)
    return ai.get_acknowledgement_status(store, alert_id)


@router.post("/alerts/{alert_id}/assign", response_model=AlertAssignmentOut)
def assign(
    alert_id: int, payload: AssignRequest,
    store: Store = Depends(get_store), user: dict = Depends(require_user),
):
    _get_alert_or_404(store, alert_id)
    row = ai.record_assignment(store, alert_id, payload.assignee_name, payload.role)
    return row


@router.post("/alerts/issue", response_model=AlertOut)
def issue_alert(payload: AlertIssueRequest, store: Store = Depends(get_store), user: dict = Depends(require_user)):
    """The real Alert Composer's issue-warning endpoint — distinct from
    /alerts/test. `detected` and `warning_issued` are recorded at issue
    time because issuing genuinely IS the detection-to-warning act in this
    manual-composer flow; every other lifecycle stage (`assessed`,
    `impact_mapped`, `assigned`, `acknowledged`, `action_started`,
    `resolved`) is left pending until the frontend calls the endpoint that
    actually performs that stage — never claimed here without something
    real backing the timestamp."""
    recipients_note = ", ".join(payload.recipients) if payload.recipients else "no recipients specified"
    reason = f"{payload.reason} (recipients: {recipients_note})"

    alert = create_alert(
        store,
        alert_type=payload.threat_type,
        severity=payload.severity,
        reason=reason,
        latitude=payload.latitude,
        longitude=payload.longitude,
        state=payload.state,
        district=payload.district,
        recommended_action=payload.action,
        risk_zone_id=payload.risk_zone_id,
    )
    alert_id = alert["id"]
    ai.record_lifecycle_stage(store, alert_id, "detected", note="Detected via manual Alert Composer issuance.")
    ai.record_lifecycle_stage(store, alert_id, "warning_issued", note=f"Warning issued to: {recipients_note}.")
    return alert
