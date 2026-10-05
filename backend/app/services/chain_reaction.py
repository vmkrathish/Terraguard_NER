"""
Landslide -> road blockage -> village isolation -> emergency access delay.

This is deterministic GIS/network logic (shapely/haversine geometry over the
Excel-backed roads/villages/hospitals tables + a road graph), NOT
LLM-generated geography, per the spec.
"""
from typing import Any

from app.core.excel_store import Store, linestring_wkt_to_coords
from app.services import geo_utils

IMPACT_RADIUS_M = 3000  # roads within this distance of a high-risk point are considered affected
ISOLATION_SEARCH_RADIUS_M = 15000  # villages within this distance are checked for isolation
VILLAGE_ROAD_CONNECT_RADIUS_M = 8000


def analyze_chain_reaction(store: Store, latitude: float, longitude: float) -> dict[str, Any]:
    roads_df = store.df("roads")
    road_lines: dict[int, list[tuple[float, float]]] = {}
    affected_roads = []
    for _, r in roads_df.iterrows():
        coords = linestring_wkt_to_coords(r["geom_wkt"])
        road_lines[int(r["id"])] = coords
        dist = geo_utils.point_to_linestring_distance_m(latitude, longitude, coords)
        if dist <= IMPACT_RADIUS_M:
            affected_roads.append({
                "id": int(r["id"]), "name": r["name"], "road_type": r["road_type"],
                "status": r["status"],
                "blocked_reason": (None if _is_missing(r.get("blocked_reason")) else r["blocked_reason"]),
                "distance_m": round(dist, 1),
            })
    affected_roads.sort(key=lambda x: x["distance_m"])
    blocked_road_ids = {r["id"] for r in affected_roads if r["status"] == "blocked"}

    villages_df = store.df("villages")
    nearby_villages = geo_utils.within_radius(villages_df, latitude, longitude, ISOLATION_SEARCH_RADIUS_M)

    isolated_villages = []
    for _, v in nearby_villages.iterrows():
        connecting_road_ids = []
        for road_id, coords in road_lines.items():
            if geo_utils.line_within_distance_of_point(coords, v["latitude"], v["longitude"], VILLAGE_ROAD_CONNECT_RADIUS_M):
                connecting_road_ids.append(road_id)
        connecting_statuses = roads_df[roads_df["id"].isin(connecting_road_ids)]["status"].tolist() if connecting_road_ids else []
        if connecting_road_ids and all(
            status == "blocked" or rid in blocked_road_ids
            for rid, status in zip(connecting_road_ids, connecting_statuses)
        ):
            isolated_villages.append({"id": int(v["id"]), "name": v["name"], "population": _clean_int(v.get("population"))})

    hospitals_df = store.df("hospitals")
    nearest_hospital_row = geo_utils.nearest_one(hospitals_df, latitude, longitude) if not hospitals_df.empty else None

    accessibility = "normal"
    if isolated_villages:
        accessibility = "severely_impaired"
    elif blocked_road_ids:
        accessibility = "delayed"

    nearest_hospital = None
    nearest_hospital_distance_km = None
    if nearest_hospital_row:
        nearest_hospital = {"name": nearest_hospital_row["name"], "distance_m": round(nearest_hospital_row["distance_m"], 1)}
        nearest_hospital_distance_km = round(nearest_hospital_row["distance_m"] / 1000, 2)

    return {
        "affected_road_segments": affected_roads,
        "affected_villages": [
            {"id": int(v["id"]), "name": v["name"], "population": _clean_int(v.get("population")),
             "distance_m": round(v["distance_m"], 1)}
            for _, v in nearby_villages.iterrows()
        ],
        "isolated_villages": isolated_villages,
        "emergency_accessibility": accessibility,
        "nearest_hospital": nearest_hospital,
        "nearest_hospital_distance_km": nearest_hospital_distance_km,
    }


def _is_missing(v) -> bool:
    try:
        import pandas as pd
        return v is None or (isinstance(v, float) and pd.isna(v))
    except Exception:  # noqa: BLE001
        return v is None


def _clean_int(v):
    if _is_missing(v):
        return None
    return int(v)
