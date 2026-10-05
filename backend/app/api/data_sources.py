"""Admin-facing status for every external data-source adapter, and a soil
property lookup endpoint. See backend/app/services/data_sources/ for the
adapters/orchestrator this wraps."""
from fastapi import APIRouter, Depends, Query

from app.core.excel_store import Store, get_store
from app.services.data_sources.orchestrator import get_soil_properties
from app.services.data_sources.registry import all_adapter_status

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("/status")
def data_sources_status():
    """Real (not assumed) configuration status for every known adapter —
    used by the admin dashboard's data-source health panel. `configured`
    reflects actual credential presence, not whether the source has ever
    been successfully called."""
    return {"adapters": all_adapter_status()}


@router.get("/soil")
def soil_properties(
    lat: float = Query(...),
    lon: float = Query(...),
    store: Store = Depends(get_store),
):
    """Static soil properties (texture, organic carbon, bulk density) via
    SoilGrids — NOT live soil moisture. See orchestrator.get_soil_properties."""
    return get_soil_properties(store, lat, lon)
