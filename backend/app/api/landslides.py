from fastapi import APIRouter, Depends

from app.core.excel_store import Store, clean_records, get_store
from app.schemas.schemas import LandslideEventOut

router = APIRouter(tags=["landslides"])


@router.get("/landslides", response_model=list[LandslideEventOut])
def list_landslides(state: str | None = None, limit: int = 500, store: Store = Depends(get_store)):
    df = store.df("landslide_events")
    if state:
        df = df[df["state"] == state]
    df = df.sort_values("event_date", ascending=False, na_position="last").head(limit)
    return clean_records(df.to_dict("records"))
