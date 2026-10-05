export interface EnvironmentalAnomaly {
  is_anomaly: boolean;
  anomaly_score: number;
  method: string;
  note: string;
}

export interface RiskPredictResponse {
  probability: number;
  risk_score: number;
  risk_level: "LOW" | "MODERATE" | "HIGH" | "CRITICAL";
  contributing_factors: { feature: string; contribution: number; direction: string }[];
  explainability_method: string;
  rainfall_context: Record<string, unknown>;
  model_version: string;
  disclaimer: string;
  chain_reaction_impact?: {
    affected_road_segments: unknown[];
    affected_villages: unknown[];
    isolated_villages: { id: number; name: string; population: number | null }[];
    emergency_accessibility: string;
    nearest_hospital: { name: string } | null;
    nearest_hospital_distance_km: number | null;
  } | null;
  // Live per-query output of the pre-trained anomaly-detection artifact.
  // null when the artifact is missing — never treat null as "no anomaly".
  environmental_anomaly?: EnvironmentalAnomaly | null;
}

export interface RiskWhatIfRequest {
  latitude: number;
  longitude: number;
  state?: string;
  district?: string;
  observation_month?: number;
  observation_year?: number;
  rainfall_month_actual_mm?: number;
  rainfall_month_actual_mm_scenario: number;
}

export interface RiskWhatIfResponse {
  baseline: RiskPredictResponse;
  scenario: RiskPredictResponse;
  rainfall_change_pct: number | null;
  risk_score_change: number;
}

export interface RainfallRecord {
  state: string;
  district: string | null;
  year: number;
  month: number;
  rainfall_mm: number | null;
  data_provenance: string;
}

export interface RainfallRecordsResponse {
  records: RainfallRecord[];
}

export interface RainfallShockResponse {
  state: string;
  district: string | null;
  year: number;
  month: number;
  rainfall_month_actual_mm: number | null;
  rainfall_month_climatology_mm: number | null;
  rainfall_departure_pct: number | null;
  consecutive_wet_months: number | null;
  shock_detected: boolean;
  shock_reason: string | null;
  daily_data_available: boolean;
  note: string;
}

export interface LandslideEvent {
  id: number;
  state: string | null;
  district: string | null;
  latitude: number;
  longitude: number;
  event_date: string | null;
  landslide_type: string | null;
  severity: string | null;
  trigger: string | null;
  fatality_count: number | null;
  injury_count: number | null;
  data_provenance: string;
}

// Live-weather-by-state carousel (Admin + Authority dashboards). Every
// field beyond state/city/lat/lon/status is present ONLY when status is
// "ok" — a failed fetch for one state never gets a made-up temperature or
// condition, per the backend's insufficient_data contract.
export type WeatherConditionCategory = "clear" | "cloudy" | "fog" | "rain" | "storm" | "snow";

export interface LiveWeatherState {
  state: string;
  city: string;
  lat: number;
  lon: number;
  status: "ok" | "insufficient_data";
  message?: string;
  condition_label?: string;
  condition_category?: WeatherConditionCategory;
  temperature_c?: number;
  temperature_max_today_c?: number;
  precipitation_mm_now?: number;
  precipitation_sum_today_mm?: number;
  observed_at?: string | null;
  source?: string;
  is_cached?: boolean;
}

export interface LiveWeatherResponse {
  states: LiveWeatherState[];
}

export interface RainfallCurrentResponse {
  status: "ok" | "insufficient_data";
  record: Record<string, unknown> | null;
  attempts: { source: string; status: string; detail?: string }[];
  message?: string;
}

export interface MapLayers {
  risk_zones: {
    id: number; name: string; latitude: number; longitude: number;
    radius_m: number; risk_score: number; risk_level: string; data_provenance: string;
  }[];
  landslide_events: {
    id: number; state: string; district: string; latitude: number; longitude: number;
    event_date: string | null; severity: string; landslide_type: string;
    trigger: string | null; fatality_count: number | null; injury_count: number | null;
    event_title: string | null; event_description: string | null; data_provenance: string;
  }[];
  field_reports: {
    id: number; latitude: number; longitude: number; incident_type: string;
    severity: string; description: string | null; sync_status: string; created_at: string;
  }[];
  roads: { id: number; name: string; road_type: string; status: string; blocked_reason: string | null; geojson: string; data_provenance: string }[];
  villages: { id: number; name: string; latitude: number; longitude: number; population: number | null; data_provenance: string }[];
  hospitals: { id: number; name: string; latitude: number; longitude: number; data_provenance: string }[];
  schools: { id: number; name: string; latitude: number; longitude: number; data_provenance: string }[];
  // Real per-district aggregates (never invented) — used to color map pins and
  // show "N historical events, X% high severity" without a per-district round trip.
  district_event_summary: { state: string; district: string; event_count: number; high_severity_count: number }[];
}

export interface RainfallShock {
  state: string;
  district: string | null;
  year: number;
  month: number;
  rainfall_month_actual_mm: number | null;
  rainfall_month_climatology_mm: number | null;
  rainfall_departure_pct: number | null;
  consecutive_wet_months: number | null;
  shock_detected: boolean;
  shock_reason: string | null;
  daily_data_available: boolean;
  note: string;
}

export interface FieldReport {
  id: number;
  client_report_id: string;
  reporter_name: string | null;
  latitude: number;
  longitude: number;
  incident_type: string;
  description: string | null;
  severity: string;
  photo_path: string | null;
  photo_ai_analysis: Record<string, unknown> | null;
  sync_status: string;
  created_at: string;
}

export interface RouteOut {
  coordinates: [number, number][];
  distance_km: number;
  estimated_time_minutes: number | null;
  risk_score: number;
  avoided_segments: number;
  label: string;
  // Real distance (km) from the requested source/destination point to the
  // nearest road-graph node actually used to compute this route. null when
  // the route came from the straight-line fallback (no graph node to snap
  // to). TerraGuard's bundled demo road graph is sparse — a point far from
  // any mapped road silently snaps to whatever node is closest, which can
  // make two visibly different pins produce the identical route.
  source_snap_distance_km: number | null;
  destination_snap_distance_km: number | null;
  // Plain-language warning, set only when a snap distance above is large
  // enough to be worth telling the user about.
  network_coverage_warning: string | null;
}

export interface SafeZone {
  id: number;
  name: string;
  type: "hospital" | "school" | "village";
  latitude: number;
  longitude: number;
  distance_km: number;
  inside_risk_zone: boolean;
}

export interface RouteOptimizeResponse {
  recommended_route: RouteOut;
  alternative_route: RouteOut | null;
  disclaimer: string;
  destination_safe_zone: SafeZone | null;
}

export interface Alert {
  id: number;
  alert_type: string;
  severity: string;
  latitude: number | null;
  longitude: number | null;
  state: string | null;
  district: string | null;
  risk_score: number | null;
  reason: string;
  affected_area: string | null;
  recommended_action: string | null;
  status: string;
  created_at: string;
  // Links an issued alert back to the risk_zones row it was raised from, when
  // applicable. Existing/legacy alert rows load as null — never backfilled.
  risk_zone_id: number | null;
}

/* ==========================================================================
   Alert Intelligence Center — evidence, impact, simulation, lifecycle,
   acknowledgements, threat board. See ALERT_INTELLIGENCE_BACKEND_NOTES.md
   for the exact real shapes these mirror. Never invent a confidence score,
   population figure, or count anywhere these types are consumed.
   ========================================================================== */

export interface EvidenceSignal {
  key: string;
  label: string;
  verified: boolean;
  detail: string;
}

export interface Evidence {
  signals: EvidenceSignal[];
  verified_count: number;
  total_count: number;
}

export interface ImpactVillage {
  id: number;
  name: string;
  population: number | null;
  distance_m: number;
}

export interface ImpactRoad {
  id: number;
  name: string;
  status: string;
  distance_m: number;
}

export interface ImpactFacility {
  id: number;
  name: string;
  distance_m: number;
}

export interface SafeZoneImpact {
  id: number;
  name: string;
  type: "hospital" | "school" | "village";
  latitude: number;
  longitude: number;
  distance_km: number;
  inside_risk_zone: boolean;
  route_if_road_blocked: RouteOut | null;
}

export interface ImpactAssessment {
  affected_villages: ImpactVillage[];
  affected_roads: ImpactRoad[];
  affected_hospitals: ImpactFacility[];
  affected_schools: ImpactFacility[];
  total_population_known: number | null;
  population_note: string | null;
  safe_zone: SafeZoneImpact | null;
  scenario: boolean | null;
  scenario_description: string | null;
}

export interface ThreatImpactSummary {
  village_count: number;
  road_count: number;
  facility_count: number;
}

export interface ThreatEntry {
  risk_zone_id: number;
  name: string;
  state: string;
  district: string;
  latitude: number;
  longitude: number;
  risk_level: string;
  risk_score: number;
  evidence: Evidence;
  impact_summary: ThreatImpactSummary;
  latest_alert: Alert | null;
}

// The 8 canonical stages, in order — mirrors alert_intelligence.LIFECYCLE_STAGES.
export const LIFECYCLE_STAGES = [
  "detected",
  "assessed",
  "impact_mapped",
  "assigned",
  "warning_issued",
  "acknowledged",
  "action_started",
  "resolved",
] as const;

export type LifecycleStage = (typeof LIFECYCLE_STAGES)[number];

export interface LifecycleStageEntry {
  stage: string;
  status: "done" | "pending";
  occurred_at: string | null;
  note: string | null;
}

export type AckRole = "field_officer" | "authority" | "admin" | "community" | "emergency_team";

export interface AcknowledgementStatus {
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  channel_type: "real_role" | "simulation";
}

export type AcknowledgementMap = Record<AckRole, AcknowledgementStatus>;

export interface AssignmentOut {
  id: number;
  alert_id: number;
  assignee_name: string;
  role: string;
  assigned_at: string;
}

// A real, registered account from GET /auth/users — used to let someone be
// picked by name instead of free-typed (which could name a person with no
// account, or claim a role they don't actually hold).
export interface UserSummary {
  // A Supabase UUID string now, not an auto-increment int — authentication
  // moved from the Excel `users` sheet to a Supabase `users` table. Already
  // treated as an opaque string key wherever it's used (WarRoom.tsx does
  // `String(u.id)`), so this is not a breaking change downstream.
  id: string;
  full_name: string;
  email: string;
  role: string;
}

export interface AlertDetail {
  alert: Alert;
  evidence: Evidence;
  impact: ImpactAssessment;
  lifecycle: LifecycleStageEntry[];
  acknowledgements: AcknowledgementMap;
}

export interface SimulateScenarioRequest {
  lat: number;
  lon: number;
  radius_m: number;
  radius_multiplier?: number;
  blocked_road_id?: number;
}

export interface AlertIssueRequest {
  recipients: string[];
  threat_type: string;
  latitude: number;
  longitude: number;
  state?: string | null;
  district?: string | null;
  severity: string;
  action: string;
  risk_zone_id?: number | null;
  reason: string;
}

export interface RagIngestResponse {
  documents_ingested: number;
  chunks_created: number;
  skipped: string[];
}

export interface RagQueryResponse {
  answer: string;
  sources: { title: string; source: string | null; chunk_index: number; similarity: number; excerpt: string; page?: number | null }[];
  llm_used: boolean;
  provider: string;
  fallback_reason: string | null;
  // "general_chat" = a greeting/small-talk message, answered instantly with
  // a canned reply — no DB/RAG/LLM call. "about_app" = a question about
  // TerraGuard itself, answered instantly from a fixed description.
  // "structured" = answered directly from the Excel data store (risk zones, rainfall,
  // landslide history) — numbers here come only from real rows, never the LLM.
  // "document" = answered from the knowledge base via RAG.
  // "combined" = both, merged. "insufficient_data" = not enough information available.
  answer_type:
    | "general_chat"
    | "about_app"
    | "structured"
    | "document"
    | "combined"
    | "insufficient_data"
    | "general_knowledge";
  structured_rows: Record<string, unknown>[];
  query_description: string | null;
  // Present only when a real multi-year/month breakdown exists (currently
  // rainfall) — every cell is a real aggregate from the Excel data store, never invented.
  chart_data: {
    type: "heatmap";
    title: string;
    x_labels: string[];
    y_labels: string[];
    values: (number | null)[][];
    unit: string;
  } | null;
  // Only present when LLM_PROVIDER='multi': what happened on the chatbot's
  // Groq-primary / OpenRouter-fallback chain for this question — status,
  // groundedness, latency, and a 0-100 quality score for each provider
  // actually attempted, with `selected_as_optimal: true` on whichever one
  // was used for `answer`. Gemini never appears here — it's excluded from
  // the chat runtime entirely. A provider skipped because an earlier one
  // already succeeded shows status "not_called".
  llm_comparison: LlmComparisonEntry[] | null;
}

// Census of India 2001 Village Directory — exposure/context data only (no
// coordinates, never fed to the ML risk model). See docs/DATASET_SCHEMA_DIFF.md.
export interface VillageCensusProfile {
  record_id: string;
  state_name: string;
  district_code: number;
  village_name: string;
  village_area_hectares: number | null;
  total_households: number | null;
  population_total: number | null;
  population_male: number | null;
  population_female: number | null;
  st_population_total: number | null;
  sc_population_total: number | null;
  education_facility_available: number | null;
  medical_facility_available: number | null;
  drinking_water_facility_available: number | null;
  approach_pucca_road: number | null;
  nearest_town_name: string | null;
  distance_to_town_km: number | null;
  forest_area_hectares: number | null;
  main_crop: string | null;
  // "historical"/"verified" for a real Census 2001 row, or
  // "synthetic_generated_v1"/"synthetic_not_verified_statistical_model" for
  // a transparently-labeled synthetic row (only ever returned when the
  // search was made with include_synthetic=true) — see backend/app/api/census.py.
  data_provenance: string;
  source_name: string;
  quality_status: string;
}

export interface VillageCensusSearchResponse {
  query: Record<string, unknown>;
  matched: number;
  results: VillageCensusProfile[];
  note: string | null;
}

export interface VillageCensusCoverage {
  source: string;
  census_year: number;
  states_covered: { state_name: string; villages: number; population_total: number | null }[];
  states_not_covered: string[];
  // Real Census 2001 rows only — never moves due to the dataset's synthetic
  // augmentation. That count is reported separately below.
  synthetic_villages_available: number;
  synthetic_villages_note: string | null;
  fields_never_available_in_this_dataset: string[];
  has_coordinates: boolean;
  used_for_ml_features: boolean;
  used_for: string;
}

export interface LlmComparisonEntry {
  provider: "groq" | "openrouter" | string;
  status: "ok" | "request_failed" | "failed_groundedness_check" | "not_called";
  latency_ms?: number;
  grounded?: boolean | null;
  score?: number;
  reason?: string;
  error?: string;
  selected_as_optimal?: boolean;
}

export interface GeoReverseResponse {
  found: boolean;
  state: string | null;
  district: string | null;
  raw_state: string | null;
}
