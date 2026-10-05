"""ISRIC SoilGrids v2.0 adapter — STATIC soil property survey, NOT live soil
moisture.

Endpoint verified (2026-09) against the CRAN `soilDB` package's real
`fetchSoilGrids()` R source, which calls:
  https://rest.isric.org/soilgrids/v2.0/properties/query
  ?lon=<lon>&lat=<lat>&property=<clay|sand|silt|soc|bdod|...>
  &depth=<0-5cm|5-15cm|...>&value=mean

No API key required — ISRIC SoilGrids is a free, public global soil-property
map (250m resolution), not a live sensor network.

IMPORTANT — what this data actually IS:
  SoilGrids gives static, modeled soil PROPERTIES (texture, organic carbon,
  bulk density) from historical soil surveys and remote sensing, valid at
  roughly decadal timescales. It is documented here as
  DataKind.STATIC_SOIL_PROPERTY. It does NOT provide live/current soil
  MOISTURE. If TerraGuard needs live soil moisture and no such source is
  configured, callers must report `insufficient_data` for moisture — never
  substitute a SoilGrids property value for it.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

from app.services.data_sources.base import BaseDataSourceAdapter
from app.services.data_sources.provenance import (
    AdapterUnavailable, DataKind, DataRecord, QualityStatus,
)

BASE_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
SOURCE_KEY = "soilgrids"
DISPLAY_NAME = "ISRIC SoilGrids v2.0 — static soil property survey"

# property -> (SoilGrids conversion factor to reach the documented unit,
# normalized field name, normalized unit). SoilGrids reports scaled integer
# "mapped units" (its own documented convention, e.g. clay in g/kg *10,
# soc in dg/kg, bdod in cg/cm3) — division factors below match ISRIC's own
# published conversion table for the "mean" statistic.
PROPERTY_MAP = {
    "clay": (10.0, "clay_pct", "%"),
    "sand": (10.0, "sand_pct", "%"),
    "silt": (10.0, "silt_pct", "%"),
    "soc": (10.0, "soil_organic_carbon_g_kg", "g/kg"),
    "bdod": (100.0, "bulk_density_kg_m3", "kg/m3"),  # cg/cm3 -> kg/m3: same numeric factor
}


class SoilGridsAdapter(BaseDataSourceAdapter):
    key = SOURCE_KEY
    display_name = DISPLAY_NAME
    provides = ["soil"]

    def __init__(self, timeout_seconds: float = 20.0, http_client: Optional[httpx.Client] = None):
        self._timeout = timeout_seconds
        self._client = http_client

    def is_configured(self) -> bool:
        return True

    def _get(self, params: list[tuple[str, str]]) -> dict:
        if self._client is not None:
            resp = self._client.get(BASE_URL, params=params, timeout=self._timeout)
        else:
            resp = httpx.get(BASE_URL, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def fetch(self, lat: float, lon: float, **kwargs) -> DataRecord:
        depth = kwargs.get("depth", "0-5cm")
        properties = kwargs.get("properties") or list(PROPERTY_MAP.keys())
        params: list[tuple[str, str]] = [("lon", str(lon)), ("lat", str(lat))]
        for p in properties:
            params.append(("property", p))
        params.append(("depth", depth))
        params.append(("value", "mean"))

        try:
            payload = self._get(params)
        except Exception as exc:  # noqa: BLE001
            raise AdapterUnavailable(f"soilgrids request failed: {exc}") from exc

        try:
            layers = payload["properties"]["layers"]
        except (KeyError, TypeError) as exc:
            raise AdapterUnavailable(f"soilgrids returned an unexpected response shape: {exc}") from exc

        values: dict[str, float] = {}
        original_units: dict[str, str] = {}
        normalized_units: dict[str, str] = {}
        for layer in layers:
            prop_name = layer.get("name")
            mapping = PROPERTY_MAP.get(prop_name)
            if not mapping:
                continue
            factor, field_name, unit = mapping
            for d in layer.get("depths", []):
                if d.get("label") != depth:
                    continue
                raw = d.get("values", {}).get("mean")
                if raw is None:
                    continue
                values[field_name] = round(raw / factor, 2)
                original_units[field_name] = f"mapped_units (÷{factor:g} = {unit})"
                normalized_units[field_name] = unit

        if not values:
            raise AdapterUnavailable("soilgrids returned no usable property values for this location/depth")

        return DataRecord(
            source=self.key,
            source_name=self.display_name,
            source_url=BASE_URL,
            data_kind=DataKind.STATIC_SOIL_PROPERTY,
            quality_status=QualityStatus.OK,
            values=values,
            original_units=original_units,
            normalized_units=normalized_units,
            retrieved_at=dt.datetime.now(dt.timezone.utc),
            observed_at=None,  # static survey product, not a dated observation
            is_live=False,
            is_cached=False,
            quality_score=0.6,  # static/modeled, decadal-timescale — not live ground truth
            message=(
                "SoilGrids gives static, modeled soil texture/organic-carbon/bulk-density from "
                "historical surveys — not live soil moisture. Depth interval: " + depth
            ),
        )
