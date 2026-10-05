"""India Meteorological Department (IMD) adapter — NOT YET CONFIGURED.

IMD is the India-preferred source for ground rainfall data (it should
outrank NASA POWER in the orchestrator's priority order whenever it's
available), but IMD does not publish a single, stable, publicly-documented
REST API with a fixed URL the way NASA POWER or SoilGrids do — real access
requires either:
  - IMD's own data request/API-access process (https://mausam.imd.gov.in/
    and https://dsp.imdpune.gov.in/ — station/gridded data request, not a
    simple public key), or
  - a data.gov.in API key for the specific IMD-sourced datasets published
    there (https://www.data.gov.in/ministrydepartment/India+Meteorological+
    Department), which does use a documented `api-key` query parameter and
    a `data.gov.in` resource-id URL pattern.

Per the project's own rule ("verify current official API documentation
before implementing endpoints; never invent an API endpoint"), this
adapter is intentionally left NOT implemented against a guessed endpoint.
It raises AdapterNotConfigured until:
  1. A real data.gov.in resource ID + API key is obtained and set via
     IMD_DATA_GOV_IN_RESOURCE_ID / IMD_DATA_GOV_IN_API_KEY, or
  2. Someone verifies the exact current endpoint for direct IMD access and
     updates this file accordingly (this is exactly the kind of thing to
     flag rather than fake — see docs/DATASET_SCHEMA_DIFF.md).

The orchestrator still lists this adapter (so /health and the admin
data-sources dashboard show it as "not_configured", not silently absent),
and falls through to NASA POWER when it's unavailable.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.services.data_sources.base import BaseDataSourceAdapter
from app.services.data_sources.provenance import AdapterNotConfigured, DataRecord

settings = get_settings()


class ImdAdapter(BaseDataSourceAdapter):
    key = "imd"
    display_name = "India Meteorological Department (ground rainfall)"
    provides = ["rainfall"]

    def is_configured(self) -> bool:
        return bool(getattr(settings, "IMD_DATA_GOV_IN_RESOURCE_ID", None) and getattr(settings, "IMD_DATA_GOV_IN_API_KEY", None))

    def fetch(self, lat: float, lon: float, **kwargs) -> DataRecord:
        if not self.is_configured():
            raise AdapterNotConfigured(
                "IMD adapter requires IMD_DATA_GOV_IN_RESOURCE_ID and IMD_DATA_GOV_IN_API_KEY "
                "(a data.gov.in API key for the specific IMD rainfall dataset) — not configured. "
                "See this file's module docstring for how to obtain real credentials rather than "
                "guessing an endpoint."
            )
        # Deliberately not implemented further: doing so against a
        # resource-id URL this project has not verified with a real key
        # would risk shipping a guessed integration. Once real credentials
        # exist, implement the actual data.gov.in resource request here
        # (documented pattern: https://api.data.gov.in/resource/<resource_id>
        # ?api-key=<key>&format=json&filters[...]=...), verify the response
        # shape against a live test call, and only then remove this guard.
        raise AdapterNotConfigured(
            "IMD adapter has credentials configured but the data.gov.in request implementation "
            "has not been verified against a live response yet — refusing to guess the response "
            "shape. This is a genuine TODO, not a silent failure."
        )
