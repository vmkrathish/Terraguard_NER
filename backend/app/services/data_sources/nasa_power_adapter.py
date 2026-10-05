"""NASA POWER (Prediction Of Worldwide Energy Resources) adapter.

Endpoint verified (2026-09) directly against NASA's own POWER project
tutorial notebook and the CRAN `nasapower` R package source (both real,
independent references — not invented):
  https://power.larc.nasa.gov/api/temporal/daily/point
  ?parameters=<comma-separated>&community=<AG|RE|SB>&longitude=<lon>
  &latitude=<lat>&start=<YYYYMMDD>&end=<YYYYMMDD>&format=JSON

No API key required — this is a free, public NASA API.

IMPORTANT — what this data actually IS:
  NASA POWER is satellite/MERRA-2-REANALYSIS-derived and model-derived
  data, not a ground rain-gauge reading. It is documented here as
  DataKind.REANALYSIS, never as a "live sensor". It is intended in this
  project as a FALLBACK/climatology source when TerraGuard's own database
  and (if configured) IMD ground data are unavailable — never presented to
  a user as "IMD" or "live weather station" data. PRECTOTCORR is NASA's
  own bias-corrected total-precipitation parameter (confirmed via the
  `nasapower` package documentation), reported in mm/day.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

from app.services.data_sources.base import BaseDataSourceAdapter
from app.services.data_sources.provenance import (
    AdapterUnavailable, DataKind, DataRecord, QualityStatus,
)

BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
SOURCE_KEY = "nasa_power"
DISPLAY_NAME = "NASA POWER (LaRC) — reanalysis/climatology"


class NasaPowerAdapter(BaseDataSourceAdapter):
    key = SOURCE_KEY
    display_name = DISPLAY_NAME
    provides = ["rainfall"]

    def __init__(self, timeout_seconds: float = 15.0, http_client: Optional[httpx.Client] = None):
        self._timeout = timeout_seconds
        self._client = http_client  # injectable for tests; real httpx.Client used otherwise

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
        """Fetch daily rainfall (PRECTOTCORR, mm/day) for the last N days
        (default 7) ending yesterday (POWER data has a short latency, so
        "today" is usually not yet available)."""
        days = int(kwargs.get("days", 7))
        end = dt.date.today() - dt.timedelta(days=1)
        start = end - dt.timedelta(days=days - 1)
        params = {
            "parameters": "PRECTOTCORR",
            "community": "AG",
            "longitude": lon,
            "latitude": lat,
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
        }
        try:
            payload = self._get(params)
        except Exception as exc:  # noqa: BLE001
            raise AdapterUnavailable(f"nasa_power request failed: {exc}") from exc

        try:
            series = payload["properties"]["parameter"]["PRECTOTCORR"]
        except (KeyError, TypeError) as exc:
            raise AdapterUnavailable(f"nasa_power returned an unexpected response shape: {exc}") from exc

        # POWER uses -999 as its own documented fill value for missing days —
        # never treat that as zero rainfall.
        daily = {date: value for date, value in series.items() if value is not None and value != -999}
        if not daily:
            raise AdapterUnavailable("nasa_power returned no valid daily values for this window")

        latest_date = max(daily.keys())
        latest_value = daily[latest_date]
        total_mm = sum(daily.values())

        return DataRecord(
            source=self.key,
            source_name=self.display_name,
            source_url=BASE_URL,
            data_kind=DataKind.REANALYSIS,
            quality_status=QualityStatus.OK,
            values={
                "rainfall_mm_day_latest": latest_value,
                "rainfall_mm_total_window": round(total_mm, 2),
                "window_days": len(daily),
            },
            original_units={"rainfall_mm_day_latest": "mm/day", "rainfall_mm_total_window": "mm"},
            normalized_units={"rainfall_mm_day_latest": "mm/day", "rainfall_mm_total_window": "mm"},
            observed_at=dt.datetime.strptime(latest_date, "%Y%m%d").replace(tzinfo=dt.timezone.utc),
            valid_from=dt.datetime.strptime(start.strftime("%Y%m%d"), "%Y%m%d").replace(tzinfo=dt.timezone.utc),
            valid_to=dt.datetime.strptime(end.strftime("%Y%m%d"), "%Y%m%d").replace(tzinfo=dt.timezone.utc),
            is_live=False,
            is_cached=False,
            quality_score=0.7,  # reanalysis, not ground-truth — deliberately below a live gauge's score
            message=(
                "NASA POWER is satellite/reanalysis-derived rainfall, not a ground rain gauge. "
                "Used here as a fallback when TerraGuard's own records and IMD are unavailable."
            ),
        )
