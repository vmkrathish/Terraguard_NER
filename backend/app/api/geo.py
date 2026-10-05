"""
Reverse geocoding: turns a map-pinned latitude/longitude into a state and
district name, so the Prediction page's State/District fields update
automatically instead of the user having to type them separately from a
location they just pinned on the map.

Uses OpenStreetMap's free Nominatim reverse-geocoding service — no API key,
no account, no cost. Nominatim's usage policy asks for a descriptive
User-Agent and no more than ~1 request/second, which fits how this is
used (one lookup per manual pin/drag, not bulk). If Nominatim is
unreachable or the location can't be resolved, the endpoint returns
found=false rather than guessing — the frontend simply leaves the
State/District fields as the user last set them.
"""
import logging

import httpx
from fastapi import APIRouter

from app.schemas.schemas import GeoReverseResponse

router = APIRouter(prefix="/geo", tags=["geo"])
logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

# Canonical spelling for each NE India state this project covers, keyed by
# lowercase for matching against whatever casing/spelling Nominatim returns.
NE_STATES = {
    "assam": "Assam",
    "sikkim": "Sikkim",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "tripura": "Tripura",
    "arunachal pradesh": "Arunachal Pradesh",
}


@router.get("/reverse", response_model=GeoReverseResponse)
def reverse_geocode(lat: float, lon: float):
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10, "addressdetails": 1},
            headers={"User-Agent": "TerraGuard-NER-SIH26001 (disaster-risk-monitoring project)"},
            timeout=4.0,
        )
        resp.raise_for_status()
        data = resp.json()
        address = data.get("address", {})
    except Exception as exc:  # noqa: BLE001 — reverse geocoding is a convenience, never block the form
        logger.info("Reverse geocode lookup failed for (%s, %s): %s", lat, lon, exc)
        return GeoReverseResponse(found=False, state=None, district=None, raw_state=None)

    raw_state = address.get("state")
    matched_state = NE_STATES.get((raw_state or "").strip().lower())
    district = (
        address.get("state_district")
        or address.get("county")
        or address.get("district")
        or address.get("city_district")
    )

    return GeoReverseResponse(
        found=matched_state is not None,
        state=matched_state,
        district=district,
        raw_state=raw_state,
    )
