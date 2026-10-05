"""ISRO Bhuvan/NRSC adapter — NOT CONFIGURED.

Bhuvan (https://bhuvan.nrsc.gov.in/) exposes most of its data as OGC
WMS/WFS tiled map services and a separate token-gated API portal
(https://bhuvan-app1.nrsc.gov.in/api/), intended for map-tile/thematic-layer
display and small lookups — NOT bulk per-village/per-point downloads. A
real integration requires registering for a Bhuvan API key
(https://bhuvan.nrsc.gov.in/governance/ - "Bhuvan API" registration) and
then requesting one OGC layer/tile at a time.

This adapter is left unconfigured rather than guessing a resource path.
When real credentials are available, implement the specific thematic layer
needed (e.g. LULC, geomorphology) as a WMS GetFeatureInfo call at a known,
verified layer name — not a generic "fetch everything" call.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.services.data_sources.base import BaseDataSourceAdapter
from app.services.data_sources.provenance import AdapterNotConfigured, DataRecord

settings = get_settings()


class BhuvanAdapter(BaseDataSourceAdapter):
    key = "bhuvan"
    display_name = "ISRO Bhuvan/NRSC — optional, not yet configured"
    provides = ["terrain", "landuse"]

    def is_configured(self) -> bool:
        return bool(getattr(settings, "BHUVAN_API_KEY", None))

    def fetch(self, lat: float, lon: float, **kwargs) -> DataRecord:
        raise AdapterNotConfigured(
            "Bhuvan/NRSC adapter requires a registered BHUVAN_API_KEY and a specific, verified "
            "OGC WMS layer name — neither is configured/implemented in this MVP. Bhuvan does not "
            "expose a simple bulk-download REST endpoint, so this is intentionally left as a "
            "documented gap rather than an invented one."
        )
