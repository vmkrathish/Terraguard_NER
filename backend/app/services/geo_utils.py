"""
Spatial helpers used in place of PostGIS (`ST_Distance`, `ST_DWithin`,
`<->` KNN ordering, `ST_AsGeoJSON`, etc.) now that the data layer is plain
pandas DataFrames over an Excel workbook, not PostgreSQL/PostGIS.

Point-to-point distance uses the haversine great-circle formula (accurate
to well under 0.5% for distances in the range this app cares about — a few
metres to a few hundred kilometres). Point-to-line (road/route) distance
uses `shapely` for the line geometry, with coordinates first projected to a
local equirectangular metre grid (centered on the line's own midpoint
latitude) so `shapely`'s planar distance is a meaningfully accurate
real-world distance for the small (<1-2 degree) spans every road/route in
this project's North-East India coverage area spans — the same
"simple great-circle + shapely" combination the migration plan calls for,
not a geodesic engine, but not a naive degrees-as-metres approximation
either.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd
from shapely.geometry import LineString, Point

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lon points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_m(lat1, lon1, lat2, lon2) / 1000.0


def _local_projection(center_lat: float):
    """Returns a (lon, lat) -> (x_m, y_m) projector, accurate for small
    spans near `center_lat` (equirectangular / plate carrée approximation,
    scaled by the local metres-per-degree at that latitude)."""
    m_per_deg_lat = 111_132.92 - 559.82 * math.cos(math.radians(2 * center_lat))
    m_per_deg_lon = (math.pi / 180.0) * EARTH_RADIUS_M * math.cos(math.radians(center_lat))

    def project(lon: float, lat: float) -> tuple[float, float]:
        return (lon * m_per_deg_lon, lat * m_per_deg_lat)

    return project


def point_to_linestring_distance_m(lat: float, lon: float, coords: list[tuple[float, float]]) -> float:
    """Shortest distance (metres) from a point to a polyline given as a list
    of (lon, lat) vertices — the shapely analogue of PostGIS's
    `ST_Distance(point_geog, line_geog)`."""
    if not coords:
        return float("inf")
    if len(coords) == 1:
        return haversine_m(lat, lon, coords[0][1], coords[0][0])

    lats = [c[1] for c in coords] + [lat]
    center_lat = sum(lats) / len(lats)
    project = _local_projection(center_lat)

    line = LineString([project(lon_, lat_) for lon_, lat_ in coords])
    p = Point(project(lon, lat))
    return float(p.distance(line))


def line_within_distance_of_point(coords: list[tuple[float, float]], lat: float, lon: float, radius_m: float) -> bool:
    """The shapely/haversine analogue of `ST_DWithin(line_geog, point_geog, radius_m)`."""
    return point_to_linestring_distance_m(lat, lon, coords) <= radius_m


def within_radius(
    df: pd.DataFrame, lat: float, lon: float, radius_m: float,
    lat_col: str = "latitude", lon_col: str = "longitude",
) -> pd.DataFrame:
    """Rows of `df` whose (lat_col, lon_col) point is within `radius_m`
    metres of (lat, lon) — the pandas analogue of `WHERE ST_DWithin(geom,
    point, radius)`. Adds a `distance_m` column, sorted ascending."""
    if df.empty:
        out = df.copy()
        out["distance_m"] = pd.Series(dtype="float64")
        return out
    distances = df.apply(lambda r: haversine_m(lat, lon, r[lat_col], r[lon_col]), axis=1)
    out = df.copy()
    out["distance_m"] = distances
    out = out[out["distance_m"] <= radius_m].sort_values("distance_m").reset_index(drop=True)
    return out


def nearest(
    df: pd.DataFrame, lat: float, lon: float,
    lat_col: str = "latitude", lon_col: str = "longitude", n: int = 1,
) -> pd.DataFrame:
    """The pandas analogue of `ORDER BY geom <-> point LIMIT n` (KNN)."""
    if df.empty:
        out = df.copy()
        out["distance_m"] = pd.Series(dtype="float64")
        return out
    out = df.copy()
    out["distance_m"] = out.apply(lambda r: haversine_m(lat, lon, r[lat_col], r[lon_col]), axis=1)
    return out.sort_values("distance_m").head(n).reset_index(drop=True)


def nearest_one(
    df: pd.DataFrame, lat: float, lon: float,
    lat_col: str = "latitude", lon_col: str = "longitude",
) -> Optional[dict]:
    result = nearest(df, lat, lon, lat_col, lon_col, n=1)
    if result.empty:
        return None
    return result.iloc[0].to_dict()
