"""Simple Excel-backed cache for external data-source responses, keyed by
(source, lat/lon rounded to a grid cell, parameter, time window). Avoids
re-hitting NASA POWER/SoilGrids for the same location repeatedly, and lets
the orchestrator serve a still-fresh cached value if a provider is briefly
unavailable.

Backed by the `data_source_cache` sheet in the Excel store (was previously
a Postgres table of the same name)."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from app.core.excel_store import Store
from app.services.data_sources.provenance import DataRecord

_GRID_PRECISION = 2  # ~1.1km grid cells at the equator; adequate for daily climatology/soil data


def _grid_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, _GRID_PRECISION), round(lon, _GRID_PRECISION))


def get_cached(store: Store, source: str, lat: float, lon: float, param: str, max_age_minutes: int) -> Optional[DataRecord]:
    glat, glon = _grid_key(lat, lon)
    df = store.df("data_source_cache")
    df = df[(df["source"] == source) & (df["grid_lat"] == glat) & (df["grid_lon"] == glon) & (df["param"] == param)]
    if df.empty:
        return None
    df = df.sort_values("retrieved_at", ascending=False)
    row = df.iloc[0]
    payload = row["payload"]
    retrieved_at = row["retrieved_at"]
    if isinstance(retrieved_at, str):
        retrieved_at = dt.datetime.fromisoformat(retrieved_at)
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=dt.timezone.utc)
    age_minutes = (dt.datetime.now(dt.timezone.utc) - retrieved_at).total_seconds() / 60
    if age_minutes > max_age_minutes:
        return None

    from app.services.data_sources.provenance import DataKind, QualityStatus  # local import avoids cycle

    return DataRecord(
        source=payload["source"],
        source_name=payload["source_name"],
        source_url=payload.get("source_url"),
        data_kind=DataKind(payload["data_kind"]),
        quality_status=QualityStatus.STALE if age_minutes > 0 else QualityStatus(payload["quality_status"]),
        values=payload["values"],
        original_units=payload.get("original_units", {}),
        normalized_units=payload.get("normalized_units", {}),
        retrieved_at=retrieved_at,
        is_live=False,
        is_cached=True,
        fallback_source=payload["source"],
        quality_score=payload.get("quality_score"),
        message=f"Served from cache, {age_minutes:.0f} min old.",
    )


def set_cached(store: Store, lat: float, lon: float, param: str, record: DataRecord) -> None:
    glat, glon = _grid_key(lat, lon)
    store.insert("data_source_cache", {
        "source": record.source,
        "grid_lat": glat,
        "grid_lon": glon,
        "param": param,
        "payload": record.to_dict(),
        "retrieved_at": record.retrieved_at.isoformat() if hasattr(record.retrieved_at, "isoformat") else record.retrieved_at,
    })
