"""Sanity-range validation for values coming back from external adapters.

This is a cheap, deterministic safety net — not a substitute for trusting
the provider — that catches obviously-broken responses (a provider bug, a
unit mismatch, a parsing error) before they reach the feature pipeline or
the RAG assistant. A value outside range is never silently clamped or
corrected: it is rejected, and the caller must treat the source as
unavailable for that value.
"""
from __future__ import annotations

# (min, max) plausible ranges for the North-East India region this project
# covers. Intentionally generous — the goal is to catch garbage (negative
# rainfall, a soil percentage of 500%), not to second-guess genuine extremes.
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "rainfall_mm_day": (0.0, 1500.0),          # NE India can see very heavy daily monsoon totals
    "rainfall_mm_hr": (0.0, 300.0),
    "clay_pct": (0.0, 100.0),
    "sand_pct": (0.0, 100.0),
    "silt_pct": (0.0, 100.0),
    "soil_organic_carbon_g_kg": (0.0, 800.0),
    "bulk_density_kg_m3": (500.0, 2000.0),
    "elevation_m": (-50.0, 9000.0),            # NE India spans near-sea-level to Himalayan peaks
    "slope_percent": (0.0, 400.0),
}


def is_plausible(field: str, value: float | None) -> bool:
    if value is None:
        return False
    bounds = PLAUSIBLE_RANGES.get(field)
    if bounds is None:
        return True  # no declared range — don't block on a field we haven't characterized
    lo, hi = bounds
    return lo <= value <= hi


def validate_record_values(field_to_value: dict[str, float]) -> tuple[dict[str, float], list[str]]:
    """Returns (accepted_values, rejected_field_names). Never raises —
    callers decide what to do with a partially-rejected record (usually:
    drop the whole record and treat the source as unavailable for it,
    since a validation failure suggests something is wrong with the
    request/response, not just one field)."""
    accepted, rejected = {}, []
    for field, value in field_to_value.items():
        if is_plausible(field, value):
            accepted[field] = value
        else:
            rejected.append(field)
    return accepted, rejected
