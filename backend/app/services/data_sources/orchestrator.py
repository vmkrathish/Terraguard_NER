"""Data Acquisition / Availability Orchestrator.

Implements the project's required 10-step flow for any environmental
parameter TerraGuard needs but does not hold as a live ground-truth
database value (currently: "current" rainfall and static soil properties —
TerraGuard's own `rainfall_records` table is documented as MONTHLY
HISTORICAL data only, see rainfall_shock.py, so it is never a source of
"current" rainfall; there is no soil-moisture/soil-property table at all):

  1. Check the Excel-backed cache (data_source_cache sheet) for a still-fresh value.
  2. Determine sufficiency (present, not stale) — if sufficient, use it (step
     3) and stop; a cache hit is itself "the database", per the cache being
     Excel-backed.
  3. Use the cached value if sufficient.
  4. Otherwise, call external adapters in documented priority order
     (registry.RAINFALL_ADAPTER_PRIORITY / SOIL_ADAPTER_PRIORITY).
  5. Validate the response (validators.validate_record_values) — reject
     implausible values rather than trusting them blindly.
  6. Normalize into the canonical DataRecord schema (already done by each
     adapter).
  7. Attach provenance (already part of DataRecord — source, kind, quality,
     timestamps).
  8. Store/cache the validated record in the Excel store (data_source_cache sheet).
  9. Make it available for ML/feature use — callers decide whether to use
     it; this module never calls into the ML pipeline itself.
  10. If every step above fails, return an explicit `insufficient_data`
      result. NEVER fabricate a value and NEVER ask an LLM to guess one.

This is deliberately a thin, explicit state machine — no hidden retries,
no silent substitutions.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.config import get_settings
from app.core.excel_store import Store
from app.services.data_sources import cache as ds_cache
from app.services.data_sources.provenance import AdapterNotConfigured, AdapterUnavailable, DataRecord
from app.services.data_sources.registry import (
    LIVE_WEATHER_ADAPTER_PRIORITY, RAINFALL_ADAPTER_PRIORITY, SOIL_ADAPTER_PRIORITY, get_adapter,
)
from app.services.data_sources.validators import validate_record_values

settings = get_settings()


def _try_adapters(priority: list[str], lat: float, lon: float, **kwargs) -> tuple[Optional[DataRecord], list[dict]]:
    attempts: list[dict] = []
    for key in priority:
        adapter = get_adapter(key)
        if adapter is None:
            continue
        if not adapter.is_configured():
            attempts.append({"source": key, "status": "not_configured"})
            continue
        try:
            record = adapter.fetch(lat, lon, **kwargs)
        except AdapterNotConfigured as exc:
            attempts.append({"source": key, "status": "not_configured", "detail": str(exc)})
            continue
        except AdapterUnavailable as exc:
            attempts.append({"source": key, "status": "unavailable", "detail": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 — any unexpected adapter bug must not crash the caller
            attempts.append({"source": key, "status": "error", "detail": str(exc)})
            continue

        accepted, rejected = validate_record_values(record.values)
        if not accepted:
            attempts.append({"source": key, "status": "rejected_implausible", "rejected_fields": rejected})
            continue
        record.values = accepted
        attempts.append({"source": key, "status": "ok"})
        return record, attempts
    return None, attempts


def get_current_rainfall(store: Store, lat: float, lon: float) -> dict[str, Any]:
    """Steps 1-10 for CURRENT rainfall. TerraGuard's own rainfall_records
    table is historical-monthly only (see rainfall_shock.py) — it is never
    consulted here for "current" rainfall, since it structurally cannot
    answer that question. Historical-monthly questions should keep using
    rainfall_shock.py / the /rainfall endpoints directly, not this
    function."""
    cached = ds_cache.get_cached(
        store, source="nasa_power", lat=lat, lon=lon, param="rainfall",
        max_age_minutes=settings.DATA_SOURCE_CACHE_RAINFALL_MAX_AGE_MINUTES,
    )
    if cached is not None:
        return {"status": "ok", "record": cached.to_dict(), "attempts": [{"source": "cache", "status": "hit"}]}

    record, attempts = _try_adapters(RAINFALL_ADAPTER_PRIORITY, lat, lon)
    if record is None:
        return {
            "status": "insufficient_data",
            "record": None,
            "attempts": attempts,
            "message": (
                "No current rainfall value is available: TerraGuard's records only hold "
                "historical monthly rainfall, and every configured external source "
                "(IMD, NASA POWER) is either not configured or unavailable right now."
            ),
        }
    ds_cache.set_cached(store, lat, lon, "rainfall", record)
    return {"status": "ok", "record": record.to_dict(), "attempts": attempts}


def get_soil_properties(store: Store, lat: float, lon: float) -> dict[str, Any]:
    """Steps 1-10 for static soil properties. TerraGuard has no
    soil-property table at all today, so the DB-check step always misses
    and this always consults the cache/adapter chain — that is honest
    behavior, not a bug: see database/migrations/003 for why the village
    census dataset's soil_characters column can never fill this role."""
    cached = ds_cache.get_cached(
        store, source="soilgrids", lat=lat, lon=lon, param="soil",
        max_age_minutes=settings.DATA_SOURCE_CACHE_SOIL_MAX_AGE_MINUTES,
    )
    if cached is not None:
        return {"status": "ok", "record": cached.to_dict(), "attempts": [{"source": "cache", "status": "hit"}]}

    record, attempts = _try_adapters(SOIL_ADAPTER_PRIORITY, lat, lon)
    if record is None:
        return {
            "status": "insufficient_data",
            "record": None,
            "attempts": attempts,
            "message": "No soil property data is available for this location right now.",
        }
    ds_cache.set_cached(store, lat, lon, "soil", record)
    return {"status": "ok", "record": record.to_dict(), "attempts": attempts}


def get_live_weather(store: Store, lat: float, lon: float) -> dict[str, Any]:
    """Steps 1-10 for LIVE current weather conditions at one point (used by
    the dashboard's live-weather-by-state carousel). Unlike rainfall/soil,
    there is no Excel ground-truth table this could ever be an alternative
    to — it always goes cache -> adapter chain -> insufficient_data, same
    shape as get_soil_properties above, just with a much shorter cache
    window since "live" conditions go stale within minutes, not months."""
    cached = ds_cache.get_cached(
        store, source="open_meteo", lat=lat, lon=lon, param="live_weather",
        max_age_minutes=settings.DATA_SOURCE_CACHE_LIVE_WEATHER_MAX_AGE_MINUTES,
    )
    if cached is not None:
        return {"status": "ok", "record": cached.to_dict(), "attempts": [{"source": "cache", "status": "hit"}]}

    record, attempts = _try_adapters(LIVE_WEATHER_ADAPTER_PRIORITY, lat, lon)
    if record is None:
        return {
            "status": "insufficient_data",
            "record": None,
            "attempts": attempts,
            "message": "No live weather data is available for this location right now.",
        }
    ds_cache.set_cached(store, lat, lon, "live_weather", record)
    return {"status": "ok", "record": record.to_dict(), "attempts": attempts}
