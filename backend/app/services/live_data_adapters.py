"""
Live-data adapters: Live API -> adapter -> normalizer -> database -> risk engine.

Each adapter is a clean interface for a FUTURE live integration (IMD/weather,
Sentinel/Copernicus satellite, soil moisture). None of them fabricate data.
Without external credentials configured, each returns a clearly-labelled
"not configured" result rather than crashing the application, and any
external API failure (timeout, non-200, network error) is caught and
returned the same way.
"""
from typing import Any, Optional

import httpx

from app.core.config import get_settings

settings = get_settings()


def _not_configured(name: str) -> dict[str, Any]:
    return {
        "status": "not_configured",
        "source": name,
        "data": None,
        "message": f"{name} live adapter has no API URL/key configured. Running in local/demo mode.",
    }


def _failed(name: str, exc: Exception) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "source": name,
        "data": None,
        "message": f"{name} live adapter call failed: {exc}. Falling back to historical data only.",
    }


def fetch_live_rainfall(lat: float, lon: float) -> dict[str, Any]:
    """IMD / weather-provider daily rainfall adapter (interface for future use)."""
    if not settings.IMD_LIVE_RAINFALL_URL:
        return _not_configured("imd_live_rainfall")
    try:
        resp = httpx.get(
            settings.IMD_LIVE_RAINFALL_URL, params={"lat": lat, "lon": lon}, timeout=5.0
        )
        resp.raise_for_status()
        return {"status": "ok", "source": "imd_live_rainfall", "data": resp.json(), "message": None}
    except Exception as exc:  # noqa: BLE001
        return _failed("imd_live_rainfall", exc)


def fetch_satellite_observation(lat: float, lon: float) -> dict[str, Any]:
    """Sentinel/Copernicus adapter (interface for future use)."""
    if not settings.SATELLITE_API_URL:
        return _not_configured("sentinel_copernicus")
    try:
        headers = {}
        if settings.SATELLITE_API_KEY:
            headers["Authorization"] = f"Bearer {settings.SATELLITE_API_KEY}"
        resp = httpx.get(
            settings.SATELLITE_API_URL, params={"lat": lat, "lon": lon}, headers=headers, timeout=8.0
        )
        resp.raise_for_status()
        return {"status": "ok", "source": "sentinel_copernicus", "data": resp.json(), "message": None}
    except Exception as exc:  # noqa: BLE001
        return _failed("sentinel_copernicus", exc)


def fetch_soil_moisture(lat: float, lon: float) -> dict[str, Any]:
    """Optional soil-moisture adapter (interface for future use)."""
    return _not_configured("soil_moisture")
