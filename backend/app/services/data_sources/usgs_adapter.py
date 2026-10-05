"""USGS adapter — contextual/secondary source, NOT CONFIGURED for this MVP.

The spec calls for USGS only as a contextual/secondary source requiring
"scientific justification matching model training schema" — TerraGuard's
current XGBoost model does not use any USGS-sourced feature, so there is no
justified integration point yet. Real USGS APIs that WOULD be relevant if a
future feature needs them: the USGS Landslide Inventory
(https://www.usgs.gov/programs/landslide-hazards) for global historical
event context, and USGS Earthquake Hazards Program's real-time feed
(https://earthquake.usgs.gov/earthquake/feed/v1.0/geojson.php) for
seismic-trigger context, both real documented public APIs. Neither is
wired in here because neither has a validated place in the current feature
set — flagged rather than added speculatively.
"""
from __future__ import annotations

from app.services.data_sources.base import BaseDataSourceAdapter
from app.services.data_sources.provenance import AdapterNotConfigured, DataRecord


class UsgsAdapter(BaseDataSourceAdapter):
    key = "usgs"
    display_name = "USGS — contextual/secondary, not yet integrated"
    provides = []

    def is_configured(self) -> bool:
        return False

    def fetch(self, lat: float, lon: float, **kwargs) -> DataRecord:
        raise AdapterNotConfigured(
            "USGS is not wired into any TerraGuard feature — the current model has no "
            "USGS-sourced input to justify integrating it yet. See this file's docstring for "
            "the real, verified endpoints to use if a future feature needs seismic-trigger or "
            "global landslide-inventory context."
        )
