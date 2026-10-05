from fastapi import APIRouter, Depends, HTTPException

from app.core.excel_store import Store, get_store
from app.services.route_optimizer import find_nearest_safe_zone, optimize_route
from app.schemas.schemas import (
    NearestSafeZoneRequest,
    RouteOptimizeRequest,
    RouteOptimizeResponse,
    SafeZoneOut,
)

router = APIRouter(tags=["route"])


@router.post("/route/nearest-safe-zone", response_model=SafeZoneOut)
def nearest_safe_zone(payload: NearestSafeZoneRequest, store: Store = Depends(get_store)):
    """Finds the nearest hospital/school/village that is NOT currently
    inside a HIGH/CRITICAL risk zone — used as the default evacuation
    destination when the user hasn't picked one."""
    result = find_nearest_safe_zone(store, payload.lat, payload.lon, emergency_type=payload.emergency_type)
    if result is None:
        raise HTTPException(status_code=404, detail="No candidate evacuation point exists in TerraGuard's records.")
    return {
        "id": result["id"],
        "name": result["name"],
        "type": result["type"],
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "distance_km": round(result["distance_m"] / 1000, 2),
        "inside_risk_zone": result["inside_risk_zone"],
    }


@router.post("/route/optimize", response_model=RouteOptimizeResponse)
def route_optimize(payload: RouteOptimizeRequest, store: Store = Depends(get_store)):
    destination_safe_zone = None
    dest_lat, dest_lon = payload.dest_lat, payload.dest_lon

    if payload.to_nearest_safe_zone:
        zone = find_nearest_safe_zone(store, payload.source_lat, payload.source_lon, emergency_type=payload.emergency_type)
        if zone is None:
            raise HTTPException(status_code=404, detail="No candidate evacuation point exists in TerraGuard's records.")
        dest_lat, dest_lon = zone["latitude"], zone["longitude"]
        destination_safe_zone = {
            "id": zone["id"],
            "name": zone["name"],
            "type": zone["type"],
            "latitude": zone["latitude"],
            "longitude": zone["longitude"],
            "distance_km": round(zone["distance_m"] / 1000, 2),
            "inside_risk_zone": zone["inside_risk_zone"],
        }
    elif dest_lat is None or dest_lon is None:
        raise HTTPException(status_code=422, detail="Provide dest_lat/dest_lon, or set to_nearest_safe_zone=true.")

    result = optimize_route(store, payload.source_lat, payload.source_lon, dest_lat, dest_lon, payload.emergency_type)
    result["destination_safe_zone"] = destination_safe_zone
    return result
