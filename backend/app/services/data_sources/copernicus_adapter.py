"""Copernicus/Sentinel adapter — NOT CONFIGURED (optional, credentials-gated).

Real official access point (verified): Copernicus Data Space Ecosystem,
https://dataspace.copernicus.eu/ — OAuth2 client-credentials auth against
https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token,
then OData/STAC product search at
https://catalogue.dataspace.copernicus.eu/odata/v1/Products. This requires
a free Copernicus Data Space account (CLIENT_ID/CLIENT_SECRET) — there is
no keyless public endpoint.

Per the spec's own explicit multi-step requirement for this source
(retrieve metadata -> validate availability -> cloud/quality filter ->
process -> generate ONE clearly-defined derived feature -> store with
provenance -> feed into ML ONLY if the trained model was trained with that
feature), this is properly a multi-day integration involving real Sentinel
product processing (e.g. Sentinel-1 InSAR coherence/deformation, or
Sentinel-2 NDVI/land-cover change) — not something to fake with a single
adapter call. This module defines the real auth/search endpoints (so the
integration can be built directly on top of it later) and honestly reports
`not_configured` / "not implemented" rather than fabricating a satellite
feature.

CRITICAL, per the project's own rule: the trained XGBoost model in this
project was NOT trained with any satellite feature. Do not wire this
adapter's output into ML inference until the model has been retrained with
a matching feature and `feature_schema_version` has been bumped — doing
otherwise would create a train/inference feature mismatch.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.services.data_sources.base import BaseDataSourceAdapter
from app.services.data_sources.provenance import AdapterNotConfigured, DataRecord

AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

settings = get_settings()


class CopernicusAdapter(BaseDataSourceAdapter):
    key = "copernicus"
    display_name = "Copernicus Data Space (Sentinel) — optional, not yet configured"
    provides = ["satellite"]

    def is_configured(self) -> bool:
        return bool(getattr(settings, "COPERNICUS_CLIENT_ID", None) and getattr(settings, "COPERNICUS_CLIENT_SECRET", None))

    def fetch(self, lat: float, lon: float, **kwargs) -> DataRecord:
        if not self.is_configured():
            raise AdapterNotConfigured(
                "Copernicus adapter requires COPERNICUS_CLIENT_ID/COPERNICUS_CLIENT_SECRET "
                "(free Copernicus Data Space Ecosystem account) — not configured. This source is "
                "optional for the MVP; TerraGuard functions fully without it."
            )
        raise AdapterNotConfigured(
            "Copernicus product retrieval/processing pipeline (metadata search -> cloud/quality "
            "filter -> derived-feature generation) is not implemented in this MVP — flagged as a "
            "real limitation rather than faking a satellite-derived value. See this file's "
            "docstring for the verified real endpoints to build against."
        )
