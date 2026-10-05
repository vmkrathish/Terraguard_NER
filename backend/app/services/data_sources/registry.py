"""Central registry of every data-source adapter this project knows about.

The orchestrator and the admin data-sources dashboard both go through this
registry rather than importing individual adapter modules directly, so
adding a new source means adding it here once.
"""
from __future__ import annotations

from app.services.data_sources.base import BaseDataSourceAdapter
from app.services.data_sources.bhuvan_adapter import BhuvanAdapter
from app.services.data_sources.copernicus_adapter import CopernicusAdapter
from app.services.data_sources.imd_adapter import ImdAdapter
from app.services.data_sources.nasa_power_adapter import NasaPowerAdapter
from app.services.data_sources.open_meteo_adapter import OpenMeteoAdapter
from app.services.data_sources.osm_adapter import OsmAdapter
from app.services.data_sources.soilgrids_adapter import SoilGridsAdapter
from app.services.data_sources.usgs_adapter import UsgsAdapter

# Priority order for rainfall: IMD (India-preferred ground data) before
# NASA POWER (reanalysis fallback) — see orchestrator.py.
RAINFALL_ADAPTER_PRIORITY = ["imd", "nasa_power"]
SOIL_ADAPTER_PRIORITY = ["soilgrids"]
# Live current-conditions weather (dashboard carousel) — single source today;
# a list so a second live-weather provider can be added as a fallback later
# without changing any caller.
LIVE_WEATHER_ADAPTER_PRIORITY = ["open_meteo"]

_REGISTRY: dict[str, BaseDataSourceAdapter] = {}


def _build_registry() -> dict[str, BaseDataSourceAdapter]:
    adapters = [
        ImdAdapter(),
        NasaPowerAdapter(),
        SoilGridsAdapter(),
        CopernicusAdapter(),
        BhuvanAdapter(),
        OsmAdapter(),
        UsgsAdapter(),
        OpenMeteoAdapter(),
    ]
    return {a.key: a for a in adapters}


def get_registry() -> dict[str, BaseDataSourceAdapter]:
    if not _REGISTRY:
        _REGISTRY.update(_build_registry())
    return _REGISTRY


def get_adapter(key: str) -> BaseDataSourceAdapter | None:
    return get_registry().get(key)


def all_adapter_status() -> list[dict]:
    return [adapter.health_check() for adapter in get_registry().values()]
