"""Live current weather for the North-Eastern states TerraGuard covers —
backs the auto-cycling weather widget on the Admin and Authority
dashboards. See backend/app/services/data_sources/open_meteo_adapter.py
for the underlying adapter and orchestrator.get_live_weather for the
cache -> adapter -> insufficient_data flow this wraps, one state at a time.

Every value here is a real Open-Meteo response or an explicit
"insufficient_data" for that one state — never a fabricated number, per
this project's standing rule (see orchestrator.py docstring)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.excel_store import Store, get_store
from app.services.data_sources.open_meteo_adapter import decode_weather_code
from app.services.data_sources.orchestrator import get_live_weather

router = APIRouter(prefix="/weather", tags=["weather"])

# State capital (or a major town) coordinates — used only as the query point
# for "what's the weather like in <state> right now", exactly as the user
# asked ("Assam, what's condition... Tripura, what's condition..."). These
# are real, publicly known state-capital coordinates, not invented.
NE_STATES: list[dict] = [
    {"state": "Assam", "city": "Guwahati", "lat": 26.1445, "lon": 91.7362},
    {"state": "Meghalaya", "city": "Shillong", "lat": 25.5788, "lon": 91.8933},
    {"state": "Tripura", "city": "Agartala", "lat": 23.8315, "lon": 91.2868},
    {"state": "Manipur", "city": "Imphal", "lat": 24.8170, "lon": 93.9368},
    {"state": "Mizoram", "city": "Aizawl", "lat": 23.7271, "lon": 92.7176},
    {"state": "Nagaland", "city": "Kohima", "lat": 25.6751, "lon": 94.1086},
    {"state": "Arunachal Pradesh", "city": "Itanagar", "lat": 27.0844, "lon": 93.6053},
    {"state": "Sikkim", "city": "Gangtok", "lat": 27.3389, "lon": 88.6065},
]


def _shape_entry(meta: dict, result: dict) -> dict:
    entry = {
        "state": meta["state"],
        "city": meta["city"],
        "lat": meta["lat"],
        "lon": meta["lon"],
        "status": result["status"],
    }
    if result["status"] != "ok" or not result.get("record"):
        entry["message"] = result.get("message", "Live weather is unavailable for this state right now.")
        return entry

    values = result["record"]["values"]
    label, category = decode_weather_code(values.get("weather_code"))
    entry.update({
        "condition_label": label,
        "condition_category": category,  # "clear" | "cloudy" | "fog" | "rain" | "storm" | "snow"
        "temperature_c": values.get("temperature_c"),
        "temperature_max_today_c": values.get("temperature_max_today_c"),
        "precipitation_mm_now": values.get("precipitation_mm_now"),
        "precipitation_sum_today_mm": values.get("precipitation_sum_today_mm"),
        "observed_at": result["record"].get("observed_at"),
        "source": result["record"].get("source_name"),
        "is_cached": result["record"].get("is_cached", False),
    })
    return entry


@router.get("/live-states")
def live_weather_by_state(store: Store = Depends(get_store)):
    """One real Open-Meteo lookup (or a short-lived cache hit) per NE state
    TerraGuard covers. Each entry stands on its own: a failure fetching one
    state's weather never blocks or fabricates the others."""
    entries = []
    for meta in NE_STATES:
        result = get_live_weather(store, meta["lat"], meta["lon"])
        entries.append(_shape_entry(meta, result))
    return {"states": entries}
