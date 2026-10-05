"""OpenStreetMap adapter — thin registry entry over EXISTING usage.

TerraGuard already uses OpenStreetMap data for routing (a static NE-India
OSM extract feeding `route_optimizer.py`'s NetworkX graph). This
module does not duplicate that pipeline — it exists only so the
data-source registry/orchestrator can report OSM's status consistently
alongside the other sources (e.g. in the admin data-sources dashboard),
and so a future live-lookup need (a single POI/road query, rather than the
full extract) has a documented, real endpoint to build against without
overloading it:

    https://overpass-api.de/api/interpreter  (public Overpass API — rate
    limited; the project's own extract-based approach for bulk routing
    data should remain the primary path, per the spec's own instruction
    not to overload Overpass with bulk queries).

`fetch()` intentionally raises AdapterNotConfigured for point-lookups since
no live Overpass integration exists yet — road/village/hospital data
continues to come from the existing static extract and the `roads`/
`villages`/`hospitals` database tables, not from this adapter.
"""
from __future__ import annotations

from app.services.data_sources.base import BaseDataSourceAdapter
from app.services.data_sources.provenance import AdapterNotConfigured, DataRecord

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


class OsmAdapter(BaseDataSourceAdapter):
    key = "osm"
    display_name = "OpenStreetMap (static NE-India extract — existing routing pipeline)"
    provides = ["infrastructure"]

    def is_configured(self) -> bool:
        # The static extract + existing routing pipeline is always "available"
        # in the sense that it's already part of the project, not an
        # external call this adapter makes.
        return True

    def health_check(self) -> dict:
        base = super().health_check()
        base["note"] = "Backed by the existing static OSM extract + route_optimizer.py, not a live call."
        return base

    def fetch(self, lat: float, lon: float, **kwargs) -> DataRecord:
        raise AdapterNotConfigured(
            "No live Overpass point-lookup is implemented — road/village/hospital data comes "
            "from the existing static OSM extract and roads/villages/hospitals database tables. "
            "See this file's docstring for the real Overpass endpoint if a live lookup is ever "
            "genuinely needed."
        )
