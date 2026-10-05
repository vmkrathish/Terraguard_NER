import datetime as dt
import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# NOTE: password complexity (uppercase/lowercase/digit/special character) is
# deliberately NOT enforced here via a Pydantic field_validator. A validator
# raising ValueError produces FastAPI's default 422 response, whose `detail`
# is a LIST of structured error objects, not a plain string — every other
# auth error in this file (e.g. signup's 409 "email already exists") is a
# plain string, and both the web and Flutter clients render `detail`
# directly as one message. Keeping every auth error a plain string avoids a
# client having to special-case one endpoint's error shape. The actual
# complexity check lives in `app.core.security.password_strength_error`,
# called explicitly by the `/auth/signup` and `/auth/reset-password`
# endpoint functions in api/auth.py, which raise a normal
# `HTTPException(422, detail="<plain message>")` on failure — see there.


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: Optional[str] = None
    email: Optional[str] = None


class CreateUserRequest(BaseModel):
    """Account creation by an authorized existing user — self-registration
    (the old public `/auth/signup`) no longer exists at all. Deliberately
    has NO `password` field: every newly created account is assigned the
    same fixed `DEFAULT_INITIAL_PASSWORD` (see api/auth.py), shown back to
    the creator in `CreateUserResponse.initial_password` so they can pass it
    to the new user, who changes it after their first login via the
    existing `/auth/change-password`. Which roles a given caller may create
    is enforced server-side in `_can_create_role()` (api/auth.py) — this
    schema only validates shape, not permission."""
    full_name: str = Field(..., min_length=2, max_length=255)
    email: str = Field(..., min_length=5, max_length=255)
    role: str = Field(...)


class UserAccountOut(BaseModel):
    """A full account row for the Account Management screens — unlike
    `UserSummaryOut` (used by the unrelated Assign-Response picker, active
    accounts only, no status), this includes `is_active`/timestamps so an
    admin/authority can see and toggle status. Still excludes
    `password_hash`/`reset_token` — never the caller's business."""
    id: str
    full_name: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[str] = None
    last_seen: Optional[str] = None


class CreateUserResponse(UserAccountOut):
    initial_password: str


class MeResponse(BaseModel):
    """Extended for the profile mini-dashboard (id/is_active/last_seen/
    created_at added — all additive, never breaking an older client that
    only reads email/full_name/role). Deliberately still excludes
    password_hash — never returned to React/Flutter under any endpoint."""
    id: Optional[str] = None
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: Optional[bool] = None
    last_seen: Optional[str] = None
    created_at: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    """Self-service profile edit — deliberately has NO `role` or `is_active`
    field at all. This isn't just a UI choice enforced by hiding a form
    field: even a hand-crafted request that includes a `role` key has
    nothing to bind it to, since Pydantic silently drops unknown fields by
    default — the role can only ever change through a separate,
    authorized admin/user-management mechanism, never this endpoint."""
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[str] = Field(default=None, min_length=5, max_length=255)


class ProfileUpdateResponse(MeResponse):
    """Same shape as `/auth/me`, plus an optional freshly-issued JWT.

    The existing JWT's `sub` claim is the user's EMAIL (see
    `create_access_token(subject=user["email"], ...)` in login/signup) — so
    if this update changes the email, the token the client is still holding
    no longer matches any account and every subsequent request would 401.
    Rather than silently logging the user out immediately after they save
    their own profile, an email change re-issues a token bound to the new
    email; the client only needs to replace its stored token. When the
    email didn't change, this is null and nothing about the session
    changes."""
    access_token: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    # No `min_length` here — same reasoning as SignupRequest.password above:
    # `password_strength_error()` inside the endpoint is what actually
    # enforces the rule, so every failure is a plain-string 422 `detail`.
    new_password: str = Field(..., max_length=128)


class UserSummaryOut(BaseModel):
    """A real, registered account — used wherever the frontend needs to let
    someone pick a person (e.g. assigning a response), instead of accepting
    free-typed text that could name someone who doesn't actually exist or
    doesn't hold the role being assumed. Deliberately excludes
    password_hash/reset_token/is_active — those aren't the caller's business.

    `id` is a string (a Supabase UUID, e.g. "3fa8..."), not an int — the
    `users` table's primary key changed type when authentication moved from
    the Excel `users` sheet (auto-increment int) to Supabase (UUID) — see
    app/core/supabase_users.py. Both existing consumers already treat this
    id as an opaque string key (frontend/src/components/alerts/WarRoom.tsx
    does `String(u.id)`), so this is not a breaking change for either
    client."""
    id: str
    full_name: str
    email: str
    role: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ForgotPasswordResponse(BaseModel):
    message: str
    # Dev-mode only: since no email/SMTP provider is configured, the reset
    # token/link is returned directly in the response (and logged) so the
    # flow is fully testable end-to-end without external configuration.
    # Remove this field once a real email provider is wired up.
    reset_token: Optional[str] = None
    reset_link: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    token: str
    # No `min_length` here, so the 422 always carries a plain-string `detail` from
    # `password_strength_error()` inside `reset_password()`, not Pydantic's
    # own structured-list error shape.
    new_password: str = Field(..., max_length=128)


class MessageResponse(BaseModel):
    message: str


# ---------- Risk ----------
class RiskPredictRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    state: Optional[str] = None
    district: Optional[str] = None
    observation_month: Optional[int] = Field(None, ge=1, le=12)
    observation_year: Optional[int] = None
    rainfall_month_actual_mm: Optional[float] = None


class ContributingFactor(BaseModel):
    feature: str
    contribution: float
    direction: str  # "increases_risk" | "decreases_risk"


class EnvironmentalAnomaly(BaseModel):
    """Live per-query output of the pre-trained 'Unknown Trigger Hunter'
    IsolationForest artifact (scripts/train_model.py) — never retrained at
    request time, never a fabricated score."""
    is_anomaly: bool
    anomaly_score: float
    method: str
    note: str


class RiskPredictResponse(BaseModel):
    probability: float
    risk_score: float
    risk_level: str
    contributing_factors: list[ContributingFactor]
    explainability_method: str
    rainfall_context: dict[str, Any]
    model_version: str
    disclaimer: str
    chain_reaction_impact: Optional[dict[str, Any]] = None
    environmental_anomaly: Optional[EnvironmentalAnomaly] = None


class RiskWhatIfRequest(BaseModel):
    """Same inputs as RiskPredictRequest plus a hypothetical rainfall value —
    backs the read-only /risk/predict/what-if endpoint (never writes to the
    store; see RiskWhatIfResponse)."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    state: Optional[str] = None
    district: Optional[str] = None
    observation_month: Optional[int] = Field(None, ge=1, le=12)
    observation_year: Optional[int] = None
    rainfall_month_actual_mm: Optional[float] = None
    rainfall_month_actual_mm_scenario: float


class RiskWhatIfResponse(BaseModel):
    baseline: RiskPredictResponse
    scenario: RiskPredictResponse
    rainfall_change_pct: Optional[float] = None
    risk_score_change: float


# ---------- Rainfall ----------
class RainfallRecordOut(BaseModel):
    state: str
    district: Optional[str]
    year: int
    month: int
    rainfall_mm: Optional[float]
    data_provenance: str

    model_config = ConfigDict(from_attributes=True)


class RainfallShockResponse(BaseModel):
    state: str
    district: Optional[str]
    year: int
    month: int
    rainfall_month_actual_mm: Optional[float]
    rainfall_month_climatology_mm: Optional[float]
    rainfall_departure_pct: Optional[float]
    consecutive_wet_months: Optional[int]
    shock_detected: bool
    shock_reason: Optional[str]
    daily_data_available: bool = False
    note: str


# ---------- Landslide events ----------
class LandslideEventOut(BaseModel):
    id: int
    state: Optional[str]
    district: Optional[str]
    latitude: float
    longitude: float
    event_date: Optional[dt.date]
    landslide_type: Optional[str]
    severity: Optional[str]
    trigger: Optional[str]
    fatality_count: Optional[int]
    injury_count: Optional[int]
    data_provenance: str

    model_config = ConfigDict(from_attributes=True)


# ---------- Field reports ----------
class FieldReportCreate(BaseModel):
    client_report_id: Optional[uuid.UUID] = None
    reporter_name: Optional[str] = None
    reporter_contact: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    incident_type: str
    description: Optional[str] = None
    severity: str = "unknown"
    device_timestamp: Optional[dt.datetime] = None


class FieldReportOut(BaseModel):
    id: int
    client_report_id: uuid.UUID
    reporter_name: Optional[str]
    latitude: float
    longitude: float
    incident_type: str
    description: Optional[str]
    severity: str
    photo_path: Optional[str]
    photo_ai_analysis: Optional[dict]
    sync_status: str
    created_at: dt.datetime

    model_config = ConfigDict(from_attributes=True)


class ReportSyncItem(BaseModel):
    client_report_id: uuid.UUID
    reporter_name: Optional[str] = None
    reporter_contact: Optional[str] = None
    latitude: float
    longitude: float
    incident_type: str
    description: Optional[str] = None
    severity: str = "unknown"
    device_timestamp: Optional[dt.datetime] = None


class ReportSyncRequest(BaseModel):
    reports: list[ReportSyncItem]


class ReportSyncResult(BaseModel):
    client_report_id: uuid.UUID
    status: str  # "created" | "already_synced"
    server_id: int


class ReportSyncResponse(BaseModel):
    results: list[ReportSyncResult]


# ---------- Routing ----------
class RouteOptimizeRequest(BaseModel):
    source_lat: float
    source_lon: float
    # Either provide dest_lat/dest_lon directly, OR set to_nearest_safe_zone=true
    # to have the server find the nearest hospital/school/village that is
    # NOT currently inside a HIGH/CRITICAL risk zone and route there instead.
    dest_lat: Optional[float] = None
    dest_lon: Optional[float] = None
    to_nearest_safe_zone: bool = False
    emergency_type: Optional[str] = None


class SafeZoneOut(BaseModel):
    id: int
    name: str
    type: str  # "hospital" | "school" | "village"
    latitude: float
    longitude: float
    distance_km: float
    inside_risk_zone: bool  # True only in the degraded case where no fully-safe candidate exists


class NearestSafeZoneRequest(BaseModel):
    lat: float
    lon: float
    emergency_type: Optional[str] = None


class RouteSegment(BaseModel):
    from_point: list[float]
    to_point: list[float]
    risk_level: str


class RouteOut(BaseModel):
    coordinates: list[list[float]]
    distance_km: float
    estimated_time_minutes: Optional[float]
    risk_score: float
    avoided_segments: int
    label: str
    # Real distance (km) from the requested source/destination point to the
    # nearest road-graph node actually used to compute this route. None when
    # the route came from the straight-line fallback (no graph node to snap
    # to). TerraGuard's bundled demo road graph is sparse, so a point far
    # from any mapped road silently snaps to whatever node is closest —
    # these fields let the frontend say so honestly instead of hiding it.
    source_snap_distance_km: Optional[float] = None
    destination_snap_distance_km: Optional[float] = None
    # Plain-language warning, only set when a snap distance above is large
    # enough to be worth telling the user about (see NETWORK_SNAP_WARNING_KM
    # in route_optimizer.py). None when both snaps are close to the network.
    network_coverage_warning: Optional[str] = None


class RouteOptimizeResponse(BaseModel):
    recommended_route: RouteOut
    alternative_route: Optional[RouteOut]
    disclaimer: str
    destination_safe_zone: Optional[SafeZoneOut] = None


# ---------- Alerts ----------
class AlertOut(BaseModel):
    id: int
    alert_type: str
    severity: str
    latitude: Optional[float]
    longitude: Optional[float]
    state: Optional[str]
    district: Optional[str]
    risk_score: Optional[float]
    reason: str
    affected_area: Optional[str]
    recommended_action: Optional[str]
    status: str
    created_at: dt.datetime
    risk_zone_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class AlertTestRequest(BaseModel):
    alert_type: str = "test"
    severity: str = "moderate"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    reason: str = "Test alert triggered from alert-history/testing interface"


# ---------- Alert Intelligence Center ----------
class EvidenceSignal(BaseModel):
    key: str
    label: str
    verified: bool
    detail: str


class EvidenceOut(BaseModel):
    signals: list[EvidenceSignal]
    verified_count: int
    total_count: int


class AffectedVillage(BaseModel):
    id: int
    name: str
    population: Optional[int]
    distance_m: float


class AffectedRoad(BaseModel):
    id: int
    name: Optional[str]
    status: Optional[str]
    distance_m: float


class AffectedFacility(BaseModel):
    id: int
    name: str
    distance_m: float


class ImpactSafeZoneOut(BaseModel):
    id: int
    name: str
    type: str
    latitude: float
    longitude: float
    distance_km: float
    inside_risk_zone: bool
    route_if_road_blocked: Optional[dict[str, Any]] = None


class ImpactAssessmentOut(BaseModel):
    affected_villages: list[AffectedVillage]
    affected_roads: list[AffectedRoad]
    affected_hospitals: list[AffectedFacility]
    affected_schools: list[AffectedFacility]
    total_population_known: Optional[int]
    population_note: Optional[str]
    safe_zone: Optional[ImpactSafeZoneOut]
    scenario: Optional[bool] = None
    scenario_description: Optional[str] = None


class SimulateScenarioRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    radius_m: float = Field(..., gt=0)
    radius_multiplier: Optional[float] = Field(None, gt=0)
    blocked_road_id: Optional[int] = None


class LifecycleStageOut(BaseModel):
    stage: str
    status: str  # "done" | "pending"
    occurred_at: Optional[dt.datetime] = None
    note: Optional[str] = None


class LifecycleStageRequest(BaseModel):
    stage: str
    note: Optional[str] = None


class AcknowledgementChannelStatus(BaseModel):
    acknowledged: bool
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[dt.datetime] = None
    channel_type: str  # "real_role" | "simulation"


class AcknowledgeRequest(BaseModel):
    role: Optional[str] = None


class AssignRequest(BaseModel):
    assignee_name: str
    role: str


class AlertAssignmentOut(BaseModel):
    id: int
    alert_id: int
    assignee_name: str
    role: str
    assigned_at: dt.datetime


class ThreatBoardEntry(BaseModel):
    risk_zone_id: int
    name: str
    state: Optional[str]
    district: Optional[str]
    latitude: float
    longitude: float
    risk_level: str
    risk_score: Optional[float]
    evidence: EvidenceOut
    impact_summary: dict[str, int]
    latest_alert: Optional[AlertOut] = None


class AlertIssueRequest(BaseModel):
    recipients: list[str]
    threat_type: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    state: Optional[str] = None
    district: Optional[str] = None
    severity: str = "high"
    action: str
    risk_zone_id: Optional[int] = None
    reason: str


class AlertDetailOut(BaseModel):
    alert: AlertOut
    evidence: EvidenceOut
    impact: ImpactAssessmentOut
    lifecycle: list[LifecycleStageOut]
    acknowledgements: dict[str, AcknowledgementChannelStatus]


# ---------- RAG ----------
class RagQueryRequest(BaseModel):
    question: str
    top_k: int = 4


class RagSource(BaseModel):
    title: str
    source: Optional[str]
    chunk_index: int
    similarity: float
    excerpt: str
    page: Optional[int] = None


class RagQueryResponse(BaseModel):
    answer: str
    sources: list[RagSource]
    llm_used: bool
    provider: str
    fallback_reason: Optional[str] = None
    # "structured" = answered directly from the Excel-backed data store (risk zones,
    # rainfall, landslide history) — numbers here are never LLM-generated.
    # "document" = answered from knowledge_base/ via RAG.
    # "combined" = both, merged.
    # "insufficient_data" = TerraGuard's data/sources don't cover this question.
    # "general_knowledge" = TerraGuard has nothing on this question; the
    # configured multi-provider LLM chain (LLM_PROVIDER=multi) answered from
    # its own general knowledge instead — never presented as verified
    # TerraGuard data (see rag_pipeline._general_knowledge_answer).
    answer_type: str = "document"
    structured_rows: list[dict] = []
    query_description: Optional[str] = None
    # Present only for structured/combined answers where a real multi-year or
    # multi-month breakdown exists (currently: rainfall). Never invented —
    # every cell is a real aggregate computed from rainfall_records at query
    # time. Frontend renders this as a small heatmap under the reply.
    chart_data: Optional[dict] = None
    # Only present when LLM_PROVIDER='multi' and an LLM call was actually
    # made: the Groq-primary / OpenRouter-fallback chain's outcome (Gemini is
    # never called from chat) that produced `answer` — status,
    # groundedness, latency_ms, and score for each attempted provider, with
    # `selected_as_optimal: true` on the winner, and "not_called" for a
    # later provider skipped because an earlier one already succeeded. None
    # in every
    # other case (single-provider mode, or no LLM call was needed/possible).
    llm_comparison: Optional[list[dict]] = None


class RagIngestResponse(BaseModel):
    documents_ingested: int
    chunks_created: int
    skipped: list[str]


class RagReembedResponse(BaseModel):
    chunks_reembedded: int
    backend: dict


# ---------- Village census profile (Census 2001 exposure/context data) ----------
class VillageCensusProfileOut(BaseModel):
    """Read model for village_census_profile. Deliberately has NO
    lat/lon/geom (source has none) and NO risk/hazard fields — this is
    exposure/impact-assessment context, never an ML feature or risk input.
    Any of the geotechnical fields that are always NULL in this dataset are
    included so callers can see they were checked, not silently omitted."""

    model_config = ConfigDict(from_attributes=True)

    record_id: str
    state_name: str
    district_code: int
    village_name: str
    village_area_hectares: Optional[float] = None
    total_households: Optional[int] = None
    population_total: Optional[int] = None
    population_male: Optional[int] = None
    population_female: Optional[int] = None
    st_population_total: Optional[int] = None
    sc_population_total: Optional[int] = None
    education_facility_available: Optional[int] = None
    medical_facility_available: Optional[int] = None
    drinking_water_facility_available: Optional[int] = None
    approach_pucca_road: Optional[int] = None
    nearest_town_name: Optional[str] = None
    distance_to_town_km: Optional[float] = None
    forest_area_hectares: Optional[float] = None
    main_crop: Optional[str] = None
    # Always None in this dataset (source has no geotechnical survey data) —
    # present so API consumers never have to guess whether the field was
    # checked and is genuinely unavailable, vs. simply missing from the response.
    slope_percent: Optional[float] = None
    elevation_m: Optional[float] = None
    soil_characters: Optional[str] = None
    data_provenance: str
    source_name: str
    quality_status: str


class VillageCensusSearchResponse(BaseModel):
    query: dict
    matched: int
    results: list[VillageCensusProfileOut]
    note: Optional[str] = None


# ---------- Geo ----------
class GeoReverseResponse(BaseModel):
    found: bool
    state: Optional[str] = None  # one of TerraGuard's 8 covered NE India states, or None if outside/unresolved
    district: Optional[str] = None
    raw_state: Optional[str] = None  # whatever Nominatim returned, even if it didn't match a covered state
