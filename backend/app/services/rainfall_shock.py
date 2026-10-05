"""
Rainfall Shock / Anomaly Detector.

The supplied datasets contain only MONTHLY rainfall totals (no daily
resolution anywhere in the raw data) — see data/README.md. This service is
therefore honest about that: it computes shock/anomaly signals from monthly
data (departure from climatology, consecutive above-normal months) and
reports `daily_data_available: false` rather than fabricating 1-day/3-day/
7-day figures. `live_data_adapters.py` defines the interface for plugging in
real daily/live rainfall once available.
"""
from typing import Optional

import pandas as pd

from app.core.excel_store import Store

SHOCK_DEPARTURE_THRESHOLD_PCT = 60.0  # configurable heuristic, not scientifically validated

# The IMD rainfall reference table uses pre-2011 ("old scheme") district
# names, while the landslide-events/master ML dataset uses current
# (2011-census) district names — a real upstream data-harmonization gap,
# not a bug. This is a small, best-effort alias map for well-known renames
# in the NER states; it is NOT exhaustive. Unmapped districts simply won't
# match a rainfall row (queries fall back to state-level climatology only
# via the `district=None` path).
DISTRICT_ALIASES = {
    "Dima Hasao": "N. Cacha Hills (Haflong)",
    "Sonitpur": "Sonitpur (Tezpur)",
    "Darrang": "Darrang (Mangaldai)",
    "Hailakandi": "Hajlakandi",
}


def _resolve_district(district: Optional[str]) -> Optional[str]:
    if not district:
        return district
    return DISTRICT_ALIASES.get(district, district)


def get_climatology(store: Store, state: str, district: Optional[str], month: int) -> Optional[float]:
    df = store.df("rainfall_records")
    df = df[(df["state"] == state) & (df["month"] == month)]
    if district:
        df = df[df["district"] == district]
    vals = pd.to_numeric(df["rainfall_mm"], errors="coerce").dropna()
    return float(vals.mean()) if not vals.empty else None


def get_consecutive_wet_months(store: Store, state: str, district: Optional[str], year: int, month: int) -> Optional[int]:
    """Counts consecutive months (walking backward from year/month) where
    actual rainfall exceeded that month's multi-year climatology average."""
    df = store.df("rainfall_records")
    count = 0
    y, m = year, month
    for _ in range(12):
        rows = df[(df["state"] == state) & (df["year"] == y) & (df["month"] == m)]
        if district:
            rows = rows[rows["district"] == district]
        if rows.empty or pd.isna(rows.iloc[0]["rainfall_mm"]):
            break
        actual = float(rows.iloc[0]["rainfall_mm"])
        clim = get_climatology(store, state, district, m)
        if clim is None or actual <= clim:
            break
        count += 1
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return count


def detect_shock(store: Store, state: str, district: Optional[str], year: int, month: int) -> dict:
    original_district = district
    district = _resolve_district(district)
    df = store.df("rainfall_records")
    rows = df[(df["state"] == state) & (df["year"] == year) & (df["month"] == month)]
    if district:
        rows = rows[rows["district"] == district]
    actual = float(rows.iloc[0]["rainfall_mm"]) if not rows.empty and pd.notna(rows.iloc[0]["rainfall_mm"]) else None

    climatology = get_climatology(store, state, district, month)
    departure_pct = None
    if actual is not None and climatology:
        departure_pct = round((actual - climatology) / climatology * 100.0, 1)

    consecutive_wet = get_consecutive_wet_months(store, state, district, year, month) if actual is not None else None

    shock_detected = bool(departure_pct is not None and departure_pct >= SHOCK_DEPARTURE_THRESHOLD_PCT)
    shock_reason = None
    if shock_detected:
        shock_reason = (
            f"Monthly rainfall is {departure_pct}% above the long-term climatology average "
            f"for {district or state} in month {month} (threshold: {SHOCK_DEPARTURE_THRESHOLD_PCT}%)."
        )

    return {
        "state": state,
        "district": original_district,
        "year": year,
        "month": month,
        "rainfall_month_actual_mm": actual,
        "rainfall_month_climatology_mm": round(climatology, 1) if climatology else None,
        "rainfall_departure_pct": departure_pct,
        "consecutive_wet_months": consecutive_wet,
        "shock_detected": shock_detected,
        "shock_reason": shock_reason,
        "daily_data_available": False,
        "note": (
            "Only monthly rainfall totals are available in the current data source. "
            "1-day/3-day/7-day antecedent rainfall figures are not fabricated; they will "
            "populate automatically once a daily-resolution feed is connected via "
            "backend/app/services/live_data_adapters.py."
        ),
    }
