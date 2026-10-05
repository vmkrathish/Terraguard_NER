import json

import pandas as pd
from fastapi import APIRouter, Depends

from app.core.excel_store import Store, clean_records, get_store, linestring_wkt_to_coords

router = APIRouter(tags=["map"])


def _records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    if df.empty:
        return []
    out = df[cols].copy()
    return clean_records(out.to_dict("records"))


@router.get("/map/layers")
def get_map_layers(store: Store = Depends(get_store)):
    risk_zones = _records(
        store.df("risk_zones"),
        ["id", "name", "latitude", "longitude", "radius_m", "risk_score", "risk_level", "data_provenance"],
    )
    events_df = store.df("landslide_events")
    events = _records(
        events_df,
        ["id", "state", "district", "latitude", "longitude", "event_date", "severity", "landslide_type",
         "trigger", "fatality_count", "injury_count", "event_title", "event_description", "data_provenance"],
    )

    # Per-district real event counts + severity breakdown, computed once here
    # rather than duplicated client-side.
    district_summary = []
    if not events_df.empty:
        with_district = events_df[events_df["district"].notna()]
        if not with_district.empty:
            grouped = with_district.groupby(["state", "district"])
            for (state, district), g in grouped:
                high_severity = g["severity"].isin(["large", "very_large"]).sum()
                district_summary.append({
                    "state": state, "district": district,
                    "event_count": int(len(g)), "high_severity_count": int(high_severity),
                })

    reports_df = store.df("field_reports").sort_values("created_at", ascending=False, na_position="last").head(500)
    reports = _records(
        reports_df,
        ["id", "latitude", "longitude", "incident_type", "severity", "description", "sync_status", "created_at"],
    )

    roads_df = store.df("roads")
    roads = []
    for _, r in roads_df.iterrows():
        coords = linestring_wkt_to_coords(r["geom_wkt"]) if pd.notna(r.get("geom_wkt")) else []
        roads.append({
            "id": int(r["id"]), "name": r["name"], "road_type": r["road_type"], "status": r["status"],
            "blocked_reason": (None if pd.isna(r["blocked_reason"]) else r["blocked_reason"]),
            "geojson": json.dumps({"type": "LineString", "coordinates": [[lon, lat] for lon, lat in coords]}),
            "data_provenance": r["data_provenance"],
        })

    villages = _records(store.df("villages"), ["id", "name", "latitude", "longitude", "population", "data_provenance"])
    hospitals = _records(store.df("hospitals"), ["id", "name", "latitude", "longitude", "data_provenance"])
    schools = _records(store.df("schools"), ["id", "name", "latitude", "longitude", "data_provenance"])

    return {
        "risk_zones": risk_zones,
        "landslide_events": events,
        "field_reports": reports,
        "roads": roads,
        "villages": villages,
        "hospitals": hospitals,
        "schools": schools,
        "district_event_summary": district_summary,
    }
