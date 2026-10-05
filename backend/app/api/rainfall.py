import datetime as dt

import pandas as pd
from fastapi import APIRouter, Depends, Query

from app.core.excel_store import Store, clean_records, get_store
from app.services.rainfall_shock import _resolve_district, detect_shock
from app.services.data_sources.orchestrator import get_current_rainfall
from app.schemas.schemas import RainfallShockResponse

router = APIRouter(tags=["rainfall"])


@router.get("/rainfall")
def list_rainfall(state: str = Query(...), district: str | None = None, year: int | None = None, limit: int = 100, store: Store = Depends(get_store)):
    df = store.df("rainfall_records")
    df = df[df["state"] == state]
    if district:
        df = df[df["district"] == _resolve_district(district)]
    if year:
        df = df[df["year"] == year]
    df = df.sort_values(["year", "month"], ascending=False).head(limit)
    cols = ["state", "district", "year", "month", "rainfall_mm", "data_provenance"]
    records = clean_records(df[cols].to_dict("records")) if not df.empty else []
    return {"records": records}


@router.get("/rainfall/shock", response_model=RainfallShockResponse)
def rainfall_shock(
    state: str = Query(...),
    district: str | None = None,
    year: int | None = None,
    month: int | None = None,
    store: Store = Depends(get_store),
):
    now = dt.date.today()
    result = detect_shock(store, state, district, year or now.year, month or now.month)
    return result


@router.get("/rainfall/current")
def rainfall_current(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    store: Store = Depends(get_store),
):
    """CURRENT rainfall via the data-source orchestrator (cache first, then
    IMD, then NASA POWER as an honestly-labeled reanalysis fallback).
    TerraGuard's own rainfall_records table is historical-monthly only, so
    it is never a source of "current" rainfall — see
    services/data_sources/orchestrator.py. Returns `insufficient_data`
    rather than a guess when nothing is available."""
    return get_current_rainfall(store, lat, lon)
