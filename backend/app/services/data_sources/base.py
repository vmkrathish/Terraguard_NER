"""Shared adapter interface for all external data sources.

Every adapter in this package implements `BaseDataSourceAdapter`. The
orchestrator (orchestrator.py) never talks to httpx/requests directly — it
only calls `adapter.fetch(lat, lon, **kwargs)` and gets back a DataRecord,
or an AdapterNotConfigured / AdapterUnavailable exception. This keeps every
adapter swappable and independently testable (each can be monkeypatched at
the `fetch` boundary in tests, exactly like llm_providers.py's
`_PROVIDER_FUNCS` pattern already used elsewhere in this codebase).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.services.data_sources.provenance import DataRecord


class BaseDataSourceAdapter(ABC):
    #: registry key, e.g. "nasa_power", "soilgrids", "imd"
    key: str
    #: human-readable name shown in provenance/UI
    display_name: str
    #: what kind of parameter(s) this adapter provides, e.g. ["rainfall"]
    provides: list[str]

    @abstractmethod
    def is_configured(self) -> bool:
        """True if this adapter has everything it needs to attempt a real
        call (API key/credentials where required). Public no-key APIs
        (NASA POWER, SoilGrids) are always configured."""
        raise NotImplementedError

    @abstractmethod
    def fetch(self, lat: float, lon: float, **kwargs) -> DataRecord:
        """Fetch and return ONE normalized, provenance-tagged DataRecord.
        Must raise AdapterNotConfigured or AdapterUnavailable rather than
        returning a guessed/partial value silently."""
        raise NotImplementedError

    def health_check(self) -> dict:
        """Lightweight status used by /health and the admin data-sources
        dashboard. Does NOT make a real network call by default — override
        for adapters where a cheap real check is worth it."""
        return {
            "source": self.key,
            "display_name": self.display_name,
            "configured": self.is_configured(),
            "provides": self.provides,
        }
