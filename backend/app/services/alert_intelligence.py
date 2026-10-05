"""
Alert Intelligence Center — real-data-only evidence, impact, scenario and
lifecycle logic for the Alerts feature.

STANDING RULE (see repo-wide comments elsewhere): nothing in this module
invents a confidence score, a population figure, a timestamp, or any other
ground-truth number. Every value returned here is either computed directly
from a real row in the Excel store, or an honest "no data"/"pending" marker.
Keep route functions in app/api/alerts.py thin — all the real logic lives
here, following this codebase's existing convention (see risk_engine.py,
route_optimizer.py, rainfall_shock.py).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

import pandas as pd

from app.core.excel_store import Store, clean_value, linestring_wkt_to_coords
from app.services import geo_utils
from app.services.rainfall_shock import detect_shock
from app.services.route_optimizer import find_nearest_safe_zone

# The 8 canonical Alert Intelligence Center lifecycle stages, in their
# natural order. A stage with no matching row in `alert_lifecycle_events`
# for a given alert_id is "pending" — this list is the single source of
# truth both the API layer and any validation import.
LIFECYCLE_STAGES: list[str] = [
    "detected",
    "assessed",
    "impact_mapped",
    "assigned",
    "warning_issued",
    "acknowledged",
    "action_started",
    "resolved",
]

# Roles that map to real TerraGuard user accounts (the `users.role` column).
REAL_ACK_ROLES = ("field_officer", "authority", "admin")
# Channels with no real account/notification-delivery system behind them in
# this project — always labeled `channel_type: "simulation"` wherever they
# appear so the frontend never presents them as a real delivery confirmation.
SIMULATION_ACK_ROLES = ("community", "emergency_team")
ALL_ACK_ROLES = REAL_ACK_ROLES + SIMULATION_ACK_ROLES

EVIDENCE_SIGNAL_KEYS = [
    "rainfall_shock",
    "historical_landslide_activity",
    "ml_risk_elevation",
    "field_confirmation",
    "infrastructure_proximity",
]


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------- #
def compute_evidence(
    store: Store, lat: float, lon: float,
    state: Optional[str] = None, district: Optional[str] = None,
    radius_m: float = 20000,
) -> dict[str, Any]:
    """Checks exactly 5 real signals near (lat, lon) and returns each one's
    verified True/False status — never a fabricated confidence score."""
    signals: list[dict[str, Any]] = []

    # 1. rainfall_shock — only computable with a state; honest False+reason otherwise.
    if state:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            shock = detect_shock(store, state, district, now.year, now.month)
            verified = bool(shock.get("shock_detected"))
            detail = shock.get("shock_reason") or (
                "No rainfall shock detected for the current month against long-term climatology."
                if shock.get("rainfall_month_actual_mm") is not None
                else "No rainfall record available for this state/district/month."
            )
        except Exception:  # noqa: BLE001 — evidence must never crash the alert endpoints
            verified, detail = False, "Rainfall shock could not be computed for this location."
    else:
        verified, detail = False, "No state provided — rainfall shock requires a state to look up climatology."
    signals.append({
        "key": "rainfall_shock", "label": "Rainfall signal", "verified": verified, "detail": detail,
    })

    # 2. historical_landslide_activity
    events = store.df("landslide_events")
    nearby_events = geo_utils.within_radius(events, lat, lon, radius_m) if not events.empty else events
    verified = len(nearby_events) > 0
    signals.append({
        "key": "historical_landslide_activity", "label": "Historical landslide activity", "verified": verified,
        "detail": f"{len(nearby_events)} recorded landslide event(s) within {int(radius_m)}m."
        if not events.empty else "No landslide event records in the store.",
    })

    # 3. ml_risk_elevation — a nearby risk_zones row OR a recent risk_predictions row, HIGH/CRITICAL either way.
    zones = store.df("risk_zones")
    nearby_zones = geo_utils.within_radius(zones, lat, lon, radius_m) if not zones.empty else zones
    high_zones = nearby_zones[nearby_zones["risk_level"].astype(str).str.lower().isin(["high", "critical"])] if not nearby_zones.empty else nearby_zones

    preds = store.df("risk_predictions")
    nearby_preds = geo_utils.within_radius(preds, lat, lon, radius_m) if not preds.empty else preds
    high_preds = nearby_preds[nearby_preds["risk_level"].astype(str).str.lower().isin(["high", "critical"])] if not nearby_preds.empty else nearby_preds

    verified = (len(high_zones) > 0) or (len(high_preds) > 0)
    signals.append({
        "key": "ml_risk_elevation", "label": "ML/model risk elevation", "verified": verified,
        "detail": (
            f"{len(high_zones)} HIGH/CRITICAL risk zone(s) and {len(high_preds)} HIGH/CRITICAL "
            f"risk prediction(s) within {int(radius_m)}m."
        ),
    })

    # 4. field_confirmation
    reports = store.df("field_reports")
    nearby_reports = geo_utils.within_radius(reports, lat, lon, radius_m) if not reports.empty else reports
    verified = len(nearby_reports) > 0
    signals.append({
        "key": "field_confirmation", "label": "Field officer confirmation", "verified": verified,
        "detail": f"{len(nearby_reports)} field report(s) within {int(radius_m)}m."
        if not reports.empty else "No field reports in the store.",
    })

    # 5. infrastructure_proximity — any village/hospital/school within radius.
    counts = {}
    any_present = False
    for table in ("villages", "hospitals", "schools"):
        df = store.df(table)
        nearby = geo_utils.within_radius(df, lat, lon, radius_m) if not df.empty else df
        counts[table] = len(nearby)
        if len(nearby) > 0:
            any_present = True
    signals.append({
        "key": "infrastructure_proximity", "label": "Infrastructure/population proximity", "verified": any_present,
        "detail": f"{counts['villages']} village(s), {counts['hospitals']} hospital(s), "
                  f"{counts['schools']} school(s) within {int(radius_m)}m.",
    })

    verified_count = sum(1 for s in signals if s["verified"])
    return {"signals": signals, "verified_count": verified_count, "total_count": len(signals)}


# --------------------------------------------------------------------- #
# Impact
# --------------------------------------------------------------------- #
def compute_impact(store: Store, lat: float, lon: float, radius_m: float) -> dict[str, Any]:
    villages = store.df("villages")
    nearby_villages = geo_utils.within_radius(villages, lat, lon, radius_m) if not villages.empty else villages

    affected_villages = []
    known_pop_total = 0
    unknown_pop_count = 0
    for _, v in nearby_villages.iterrows():
        pop = clean_value(v.get("population"))
        if pop is None:
            unknown_pop_count += 1
        else:
            known_pop_total += int(pop)
        affected_villages.append({
            "id": int(v["id"]), "name": v["name"],
            "population": int(pop) if pop is not None else None,
            "distance_m": round(float(v["distance_m"]), 1),
        })

    total_population_known = known_pop_total if len(affected_villages) > 0 else None
    population_note = None
    if unknown_pop_count > 0:
        population_note = (
            f"population data unavailable for {unknown_pop_count} of {len(affected_villages)} "
            "affected villages; total_population_known excludes them (not counted as zero)"
        )

    roads = store.df("roads")
    affected_roads = []
    for _, r in roads.iterrows():
        try:
            coords = linestring_wkt_to_coords(r["geom_wkt"])
        except Exception:  # noqa: BLE001
            continue
        if geo_utils.line_within_distance_of_point(coords, lat, lon, radius_m):
            dist = geo_utils.point_to_linestring_distance_m(lat, lon, coords)
            affected_roads.append({
                "id": int(r["id"]), "name": r["name"], "status": r["status"],
                "distance_m": round(dist, 1),
            })
    affected_roads.sort(key=lambda r: r["distance_m"])

    hospitals = store.df("hospitals")
    nearby_hospitals = geo_utils.within_radius(hospitals, lat, lon, radius_m) if not hospitals.empty else hospitals
    affected_hospitals = [
        {"id": int(h["id"]), "name": h["name"], "distance_m": round(float(h["distance_m"]), 1)}
        for _, h in nearby_hospitals.iterrows()
    ]

    schools = store.df("schools")
    nearby_schools = geo_utils.within_radius(schools, lat, lon, radius_m) if not schools.empty else schools
    affected_schools = [
        {"id": int(s["id"]), "name": s["name"], "distance_m": round(float(s["distance_m"]), 1)}
        for _, s in nearby_schools.iterrows()
    ]

    safe_zone_raw = find_nearest_safe_zone(store, lat, lon)
    safe_zone = None
    if safe_zone_raw is not None:
        safe_zone = {
            "id": safe_zone_raw["id"], "name": safe_zone_raw["name"], "type": safe_zone_raw["type"],
            "latitude": safe_zone_raw["latitude"], "longitude": safe_zone_raw["longitude"],
            "distance_km": round(safe_zone_raw["distance_m"] / 1000, 2),
            "inside_risk_zone": safe_zone_raw["inside_risk_zone"],
        }

    return {
        "affected_villages": affected_villages,
        "affected_roads": affected_roads,
        "affected_hospitals": affected_hospitals,
        "affected_schools": affected_schools,
        "total_population_known": total_population_known,
        "population_note": population_note,
        "safe_zone": safe_zone,
    }


def impact_summary_counts(impact: dict[str, Any]) -> dict[str, int]:
    """Cheap trimmed counts for the Live Threat Board (full lists live in
    the impact-assessment/alert-detail endpoints, not the board)."""
    return {
        "village_count": len(impact["affected_villages"]),
        "road_count": len(impact["affected_roads"]),
        "facility_count": len(impact["affected_hospitals"]) + len(impact["affected_schools"]),
    }


def simulate_scenario(
    store: Store, lat: float, lon: float, radius_m: float,
    radius_multiplier: Optional[float] = None, blocked_road_id: Optional[int] = None,
) -> dict[str, Any]:
    """Pure read-only what-if computation — NEVER writes to `roads` or
    `risk_zones`. Re-derives impact with an adjusted radius and/or a
    hypothetically-blocked road, purely in memory."""
    effective_radius = radius_m * radius_multiplier if radius_multiplier else radius_m
    impact = compute_impact(store, lat, lon, effective_radius)

    description_parts = []
    if radius_multiplier:
        description_parts.append(
            f"impact radius scaled by {radius_multiplier}x (from {int(radius_m)}m to {int(effective_radius)}m)"
        )
    if blocked_road_id is not None:
        from app.services.route_optimizer import find_nearest_safe_zone as _fnsz, optimize_route as _opt

        roads = store.df("roads")
        road_row = roads[roads["id"] == blocked_road_id]
        road_name = road_row.iloc[0]["name"] if not road_row.empty else f"road id {blocked_road_id}"
        description_parts.append(f"road '{road_name}' hypothetically excluded from routing")

        safe_zone_raw = _fnsz(store, lat, lon)
        if safe_zone_raw is not None:
            route = _opt(
                store, lat, lon, safe_zone_raw["latitude"], safe_zone_raw["longitude"],
                exclude_road_id=blocked_road_id,
            )
            impact["safe_zone"] = {
                "id": safe_zone_raw["id"], "name": safe_zone_raw["name"], "type": safe_zone_raw["type"],
                "latitude": safe_zone_raw["latitude"], "longitude": safe_zone_raw["longitude"],
                "distance_km": round(safe_zone_raw["distance_m"] / 1000, 2),
                "inside_risk_zone": safe_zone_raw["inside_risk_zone"],
                "route_if_road_blocked": route["recommended_route"],
            }

    if not description_parts:
        description_parts.append("no scenario parameters changed — baseline impact recomputed")

    impact["scenario"] = True
    impact["scenario_description"] = "; ".join(description_parts)
    return impact


# --------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------- #
def get_lifecycle_timeline(store: Store, alert_id: int) -> list[dict[str, Any]]:
    events = store.df("alert_lifecycle_events")
    events = events[events["alert_id"] == alert_id] if not events.empty else events

    timeline = []
    for stage in LIFECYCLE_STAGES:
        rows = events[events["stage"] == stage] if not events.empty else events
        if not rows.empty:
            # Most recent occurrence of this stage for this alert.
            rows = rows.sort_values("occurred_at", ascending=False)
            row = rows.iloc[0]
            timeline.append({
                "stage": stage, "status": "done",
                "occurred_at": clean_value(row["occurred_at"]),
                "note": clean_value(row.get("note")),
            })
        else:
            timeline.append({"stage": stage, "status": "pending", "occurred_at": None, "note": None})
    return timeline


def record_lifecycle_stage(store: Store, alert_id: int, stage: str, note: Optional[str] = None) -> dict[str, Any]:
    if stage not in LIFECYCLE_STAGES:
        raise ValueError(f"Unknown lifecycle stage '{stage}'. Must be one of: {', '.join(LIFECYCLE_STAGES)}")
    row = store.insert("alert_lifecycle_events", {
        "alert_id": alert_id, "stage": stage, "occurred_at": _now_iso(), "note": note,
    })
    return {k: clean_value(v) for k, v in row.items()}


def has_any_lifecycle_stage(store: Store, alert_id: int) -> bool:
    events = store.df("alert_lifecycle_events")
    if events.empty:
        return False
    return bool((events["alert_id"] == alert_id).any())


# --------------------------------------------------------------------- #
# Acknowledgements
# --------------------------------------------------------------------- #
def get_acknowledgement_status(store: Store, alert_id: int) -> dict[str, Any]:
    acks = store.df("alert_acknowledgements")
    acks = acks[acks["alert_id"] == alert_id] if not acks.empty else acks

    status: dict[str, Any] = {}
    for role in ALL_ACK_ROLES:
        rows = acks[acks["role"] == role] if not acks.empty else acks
        channel_type = "simulation" if role in SIMULATION_ACK_ROLES else "real_role"
        if not rows.empty:
            rows = rows.sort_values("acknowledged_at", ascending=False)
            row = rows.iloc[0]
            status[role] = {
                "acknowledged": True,
                "acknowledged_by": clean_value(row.get("acknowledged_by")),
                "acknowledged_at": clean_value(row["acknowledged_at"]),
                "channel_type": channel_type,
            }
        else:
            status[role] = {
                "acknowledged": False, "acknowledged_by": None, "acknowledged_at": None,
                "channel_type": channel_type,
            }
    return status


def record_acknowledgement(
    store: Store, alert_id: int, role: str, acknowledged_by: Optional[str] = None,
) -> dict[str, Any]:
    if role not in ALL_ACK_ROLES:
        raise ValueError(f"Unknown acknowledgement role '{role}'. Must be one of: {', '.join(ALL_ACK_ROLES)}")

    existing = store.df("alert_acknowledgements")
    is_first_ever = existing.empty or not bool((existing["alert_id"] == alert_id).any())

    row = store.insert("alert_acknowledgements", {
        "alert_id": alert_id, "role": role, "acknowledged_by": acknowledged_by,
        "acknowledged_at": _now_iso(),
    })

    if is_first_ever:
        record_lifecycle_stage(store, alert_id, "acknowledged")

    return {k: clean_value(v) for k, v in row.items()}


def record_assignment(store: Store, alert_id: int, assignee_name: str, role: str) -> dict[str, Any]:
    existing = store.df("alert_assignments")
    is_first_ever = existing.empty or not bool((existing["alert_id"] == alert_id).any())

    row = store.insert("alert_assignments", {
        "alert_id": alert_id, "assignee_name": assignee_name, "role": role, "assigned_at": _now_iso(),
    })

    if is_first_ever:
        record_lifecycle_stage(store, alert_id, "assigned")

    return {k: clean_value(v) for k, v in row.items()}
