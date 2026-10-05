"""Provenance record shared by every external data-source adapter.

Every value this package returns MUST be wrapped in a DataRecord so callers
can tell, at a glance: where a number came from, whether it is a live
observation vs. a forecast vs. a historical/climatology fallback vs. a
static soil-survey property, when it was retrieved, and how much to trust
it. This is what lets the rest of TerraGuard (ML features, GIS badges, the
RAG assistant's provenance badge) honestly distinguish
"48.2mm LIVE - IMD - updated 4 min ago" from
"42.7mm CACHED - NASA POWER climatology - retrieved 38 min ago" instead of
presenting every number the same way.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DataKind(str, Enum):
    """What KIND of measurement this value represents — never conflate
    these. In particular: NASA POWER is REANALYSIS/MODEL-derived, not a
    live ground sensor; SoilGrids is a STATIC survey property, not live
    soil moisture."""

    LIVE_OBSERVATION = "live_observation"
    FORECAST = "forecast"
    REANALYSIS = "reanalysis"
    SATELLITE_DERIVED = "satellite_derived"
    MODEL_DERIVED = "model_derived"
    HISTORICAL = "historical"
    STATIC_SOIL_PROPERTY = "static_soil_property"
    CACHED_EXTERNAL = "cached_external"
    FIELD_REPORT = "field_report"


class QualityStatus(str, Enum):
    OK = "ok"
    STALE = "stale"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass
class DataRecord:
    """One normalized, provenance-tagged value (or small group of related
    values) returned by a data-source adapter."""

    source: str                       # adapter/registry key, e.g. "nasa_power"
    source_name: str                  # human-readable, e.g. "NASA POWER (LaRC)"
    source_url: Optional[str]         # the exact endpoint called
    data_kind: DataKind
    quality_status: QualityStatus
    values: dict[str, Any]            # normalized field name -> value
    original_units: dict[str, str] = field(default_factory=dict)
    normalized_units: dict[str, str] = field(default_factory=dict)
    retrieved_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    observed_at: Optional[dt.datetime] = None
    valid_from: Optional[dt.datetime] = None
    valid_to: Optional[dt.datetime] = None
    source_record_id: Optional[str] = None
    is_live: bool = False
    is_cached: bool = False
    fallback_source: Optional[str] = None
    quality_score: Optional[float] = None  # 0-1, adapter-specific confidence
    message: Optional[str] = None          # human-readable note, e.g. why stale/partial

    def to_dict(self) -> dict[str, Any]:
        d = {
            "source": self.source,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "data_kind": self.data_kind.value,
            "quality_status": self.quality_status.value,
            "values": self.values,
            "original_units": self.original_units,
            "normalized_units": self.normalized_units,
            "retrieved_at": self.retrieved_at.isoformat(),
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "source_record_id": self.source_record_id,
            "is_live": self.is_live,
            "is_cached": self.is_cached,
            "fallback_source": self.fallback_source,
            "quality_score": self.quality_score,
            "message": self.message,
        }
        return d


class AdapterNotConfigured(Exception):
    """Raised when an adapter needs credentials/registration that have not
    been supplied. This is NOT the same as a network failure — it means
    "this integration was implemented but nobody has configured it yet"."""


class AdapterUnavailable(Exception):
    """Raised for a real, transient failure calling a configured external
    adapter (timeout, 5xx, malformed response). Callers should fall back
    to the next source in priority order, never to a guess."""
