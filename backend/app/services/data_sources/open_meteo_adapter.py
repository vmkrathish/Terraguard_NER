"""Open-Meteo adapter — genuinely LIVE current weather conditions.

Endpoint (verified 2026-09 directly against Open-Meteo's own published API
docs, https://open-meteo.com/en/docs):
  https://api.open-meteo.com/v1/forecast
  ?latitude=<lat>&longitude=<lon>
  &current=temperature_2m,precipitation,weather_code,is_day
  &daily=temperature_2m_max,precipitation_sum
  &timezone=auto&forecast_days=1

No API key required, no rate-limit key needed for non-commercial use — this
is a free, public, keyless weather API, consistent with this project's
"no paid APIs" convention already used by nasa_power_adapter.py and
soilgrids_adapter.py.

IMPORTANT — what this data actually IS, and is NOT:
  Open-Meteo's `current` block is model-nowcast data (blended from multiple
  national weather models, refreshed roughly hourly) presented as the
  current observation for the queried point — it is the closest thing this
  project has to "is it raining right now", but it is still
  DataKind.LIVE_OBSERVATION only in the loose "current conditions" sense
  used by every public weather app; it is NOT a ground rain-gauge reading
  the way an IMD station report would be. The `daily` block's
  `temperature_2m_max` / `precipitation_sum` are same-day FORECAST values
  (today's expected high / today's expected total rainfall), not
  historical fact — used here only to answer "how much rain can be
  expected" / "how high can the temperature go today", exactly as the user
  asked, never presented as anything already observed.

WMO weather codes (the `weather_code` field) are decoded via the small
table below, taken directly from Open-Meteo's own published WMO code
table (https://open-meteo.com/en/docs -> "WMO Weather interpretation
codes"), not guessed.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

from app.services.data_sources.base import BaseDataSourceAdapter
from app.services.data_sources.provenance import (
    AdapterUnavailable, DataKind, DataRecord, QualityStatus,
)

BASE_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE_KEY = "open_meteo"
DISPLAY_NAME = "Open-Meteo — live current conditions"

# WMO weather_code -> (human label, broad category for UI animation choice).
# Category is one of: "clear", "cloudy", "fog", "rain", "storm", "snow".
_WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "clear"),
    1: ("Mainly clear", "clear"),
    2: ("Partly cloudy", "cloudy"),
    3: ("Overcast", "cloudy"),
    45: ("Fog", "fog"),
    48: ("Depositing rime fog", "fog"),
    51: ("Light drizzle", "rain"),
    53: ("Moderate drizzle", "rain"),
    55: ("Dense drizzle", "rain"),
    56: ("Light freezing drizzle", "rain"),
    57: ("Dense freezing drizzle", "rain"),
    61: ("Slight rain", "rain"),
    63: ("Moderate rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Light freezing rain", "rain"),
    67: ("Heavy freezing rain", "rain"),
    71: ("Slight snow fall", "snow"),
    73: ("Moderate snow fall", "snow"),
    75: ("Heavy snow fall", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Slight rain showers", "rain"),
    81: ("Moderate rain showers", "rain"),
    82: ("Violent rain showers", "rain"),
    85: ("Slight snow showers", "snow"),
    86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "storm"),
    96: ("Thunderstorm with slight hail", "storm"),
    99: ("Thunderstorm with heavy hail", "storm"),
}


def decode_weather_code(code: Optional[int]) -> tuple[str, str]:
    if code is None:
        return ("Unknown", "cloudy")
    return _WMO_CODES.get(int(code), (f"Unrecognized WMO code {code}", "cloudy"))


class OpenMeteoAdapter(BaseDataSourceAdapter):
    key = SOURCE_KEY
    display_name = DISPLAY_NAME
    provides = ["live_weather"]

    def __init__(self, timeout_seconds: float = 10.0, http_client: Optional[httpx.Client] = None):
        self._timeout = timeout_seconds
        self._client = http_client  # injectable for tests

    def is_configured(self) -> bool:
        return True  # public API, no credentials needed

    def _get(self, params: dict) -> dict:
        if self._client is not None:
            resp = self._client.get(BASE_URL, params=params, timeout=self._timeout)
        else:
            resp = httpx.get(BASE_URL, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def fetch(self, lat: float, lon: float, **kwargs) -> DataRecord:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,precipitation,weather_code,is_day",
            "daily": "temperature_2m_max,precipitation_sum",
            "timezone": "auto",
            "forecast_days": 1,
        }
        try:
            payload = self._get(params)
        except Exception as exc:  # noqa: BLE001
            raise AdapterUnavailable(f"open_meteo request failed: {exc}") from exc

        try:
            current = payload["current"]
            daily = payload["daily"]
            temp_now = float(current["temperature_2m"])
            precip_now = float(current.get("precipitation") or 0.0)
            weather_code = current.get("weather_code")
            temp_max_today = float(daily["temperature_2m_max"][0])
            precip_sum_today = float(daily["precipitation_sum"][0] or 0.0)
            observed_at_raw = current.get("time")
        except (KeyError, TypeError, IndexError, ValueError) as exc:
            raise AdapterUnavailable(f"open_meteo returned an unexpected response shape: {exc}") from exc

        label, category = decode_weather_code(weather_code)
        observed_at = None
        if observed_at_raw:
            try:
                observed_at = dt.datetime.fromisoformat(observed_at_raw)
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=dt.timezone.utc)
            except ValueError:
                observed_at = None

        return DataRecord(
            source=self.key,
            source_name=self.display_name,
            source_url=BASE_URL,
            data_kind=DataKind.LIVE_OBSERVATION,
            quality_status=QualityStatus.OK,
            values={
                "temperature_c": round(temp_now, 1),
                "precipitation_mm_now": round(precip_now, 2),
                "weather_code": float(weather_code) if weather_code is not None else -1.0,
                "temperature_max_today_c": round(temp_max_today, 1),
                "precipitation_sum_today_mm": round(precip_sum_today, 2),
            },
            original_units={
                "temperature_c": "°C", "precipitation_mm_now": "mm",
                "temperature_max_today_c": "°C", "precipitation_sum_today_mm": "mm",
            },
            normalized_units={
                "temperature_c": "°C", "precipitation_mm_now": "mm",
                "temperature_max_today_c": "°C", "precipitation_sum_today_mm": "mm",
            },
            observed_at=observed_at,
            is_live=True,
            is_cached=False,
            quality_score=0.75,
            message=(
                f"{label} — Open-Meteo blended model nowcast, not a ground station reading. "
                "Today's high/rainfall total are same-day forecast values, not observed history."
            ),
        )
