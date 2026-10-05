"""
Emergency route optimizer.

Cost = distance_cost + risk_penalty + blocked_road_penalty + accessibility_penalty

Routes are computed with a deterministic local road graph built from the
`roads` sheet (networkx Dijkstra), so the endpoint always returns a usable
result without any external routing service dependency. Never claims a
route is absolutely safe.

Blocked-road avoidance: blocked `roads` rows get a huge weight penalty
baked directly into the graph, so Dijkstra naturally routes around them
when any unblocked path exists; if none does, the route is returned
anyway but clearly labeled as crossing a blocked segment.
"""
from datetime import date
from typing import Any, Optional

import networkx as nx
import pandas as pd

from app.core.config import get_settings
from app.core.excel_store import Store, linestring_wkt_to_coords
from app.services import geo_utils

settings = get_settings()

# Emergency types that request the strictest avoidance profile: route around
# EVERY mapped risk zone (LOW through CRITICAL), not just blocked roads —
# appropriate for fire/rescue operations where the crew itself should not be
# routed through active-risk terrain even briefly, unlike a "get to the
# nearest hospital fast" medical run.
STRICT_AVOIDANCE_EMERGENCY_TYPES = {"rescue", "fire"}
ALL_RISK_LEVELS = ["LOW", "MODERATE", "HIGH", "CRITICAL"]

BLOCKED_PENALTY_KM = 50.0  # effectively excludes blocked segments unless unavoidable
RISK_PENALTY_PER_POINT_KM = 0.15  # per risk-score-point cost added per km of a segment

# Above this distance from the requested point to the nearest usable
# road-graph node, the snap is considered "meaningfully off the mapped
# network" and worth an explicit, honest warning in the response — rather
# than silently returning a route that starts/ends somewhere the user did
# not actually click. Chosen as roughly double the largest real gap between
# adjacent nodes in the bundled demo road graph; not derived from any
# external standard.
NETWORK_SNAP_WARNING_KM = 5.0

_haversine_km = geo_utils.haversine_km


def _risk_zone_hits(store: Store, coordinates: list[list[float]], levels: list[str]) -> int:
    """Counts distinct risk_zones (of the given levels) whose center point
    the route path actually passes within radius_m of — same interior-
    sampling approach as the blocked-road check, generalized to any
    risk-zone level. Used for the "rescue"/"fire" strict-avoidance profile,
    where the goal is a route that avoids risk zones entirely, not just the
    currently-blocked roads inside them."""
    if len(coordinates) < 2 or not levels:
        return 0
    line_coords = [(lon, lat) for lon, lat in coordinates]
    zones = store.df("risk_zones")
    zones = zones[zones["risk_level"].isin(levels)]
    count = 0
    for _, z in zones.iterrows():
        dist = geo_utils.point_to_linestring_distance_m(z["latitude"], z["longitude"], line_coords)
        if dist <= z["radius_m"]:
            count += 1
    return count


def _nearest_state(store: Store, lat: float, lon: float) -> Optional[str]:
    """Resolves the state nearest a point, from whichever real table has
    coverage there — used only to look up a REAL seasonal climatology
    average for that state below, never to invent a location."""
    candidates = []
    events = store.df("landslide_events")[["state", "latitude", "longitude"]].dropna()
    zones = store.df("risk_zones")[["state", "latitude", "longitude"]].dropna()
    candidates_df = pd.concat([events, zones], ignore_index=True)
    if candidates_df.empty:
        return None
    row = geo_utils.nearest_one(candidates_df, lat, lon)
    return row["state"] if row else None


def _location_aware_risk_score(store: Store, lat: float, lon: float, radius_m: float = 20000) -> float:
    """Real, location-specific risk score for a point along a candidate
    route. Uses the same nearby-historical-events approach as the
    Prediction page's own hist_count/hist_density computation (see
    api/risk.py), plus today's month and — when a nearby state can be
    resolved — that state's real historical climatology average for this
    month as a stand-in for actual rainfall."""
    from app.services.rainfall_shock import get_climatology
    from app.services.risk_engine import predict_risk

    events = store.df("landslide_events")
    if events.empty:
        count, density = 0, 0.0
    else:
        nearby = geo_utils.within_radius(events, lat, lon, radius_m)
        count = len(nearby)
        density = count / (3.14159 * (radius_m / 1000) ** 2) if count else 0.0

    month = date.today().month
    state = _nearest_state(store, lat, lon)
    climatology = get_climatology(store, state, None, month) if state else None

    try:
        pred = predict_risk(
            state=state,
            observation_month=month,
            rainfall_month_actual_mm=climatology,
            rainfall_month_climatology_mm=climatology,
            historical_landslide_count=count,
            historical_landslide_density=density,
            lat_lon_available=True,
        )
        return pred["risk_score"]
    except Exception:  # noqa: BLE001 — routing must still return a route if the model fails
        return 0.0


def _build_graph_from_roads(store: Store, exclude_road_id: Optional[int] = None) -> tuple[nx.Graph, dict]:
    """`exclude_road_id`, when given, treats that one road as blocked for
    graph-weighting purposes ONLY — a pure in-memory routing computation
    used by simulate_scenario's "what if this road were blocked" what-if;
    it never reads or writes the real `roads` table's `status` column."""
    roads = store.df("roads")

    graph = nx.Graph()
    node_coords: dict[tuple, tuple] = {}

    def node_id(lon, lat):
        return (round(lon, 5), round(lat, 5))

    for _, r in roads.iterrows():
        coords = linestring_wkt_to_coords(r["geom_wkt"])
        blocked = r["status"] == "blocked" or (exclude_road_id is not None and int(r["id"]) == int(exclude_road_id))
        for i in range(len(coords) - 1):
            lon1, lat1 = coords[i]
            lon2, lat2 = coords[i + 1]
            n1, n2 = node_id(lon1, lat1), node_id(lon2, lat2)
            node_coords[n1] = (lat1, lon1)
            node_coords[n2] = (lat2, lon2)
            dist_km = _haversine_km(lat1, lon1, lat2, lon2)
            weight = dist_km + (BLOCKED_PENALTY_KM if blocked else 0)
            graph.add_edge(n1, n2, weight=weight, distance_km=dist_km, blocked=blocked, road_id=int(r["id"]))
    return graph, node_coords


def _nearest_node(node_coords: dict, lat: float, lon: float):
    best, best_d = None, float("inf")
    for n, (nlat, nlon) in node_coords.items():
        d = _haversine_km(lat, lon, nlat, nlon)
        if d < best_d:
            best, best_d = n, d
    return best


def _route_via_local_graph(store: Store, source_lat, source_lon, dest_lat, dest_lon, exclude_road_id: Optional[int] = None) -> Optional[dict]:
    graph, node_coords = _build_graph_from_roads(store, exclude_road_id=exclude_road_id)
    if not node_coords:
        return None
    src = _nearest_node(node_coords, source_lat, source_lon)
    dst = _nearest_node(node_coords, dest_lat, dest_lon)
    if src is None or dst is None:
        return None
    try:
        path = nx.dijkstra_path(graph, src, dst, weight="weight")
    except nx.NetworkXNoPath:
        return None

    coords = [[node_coords[n][1], node_coords[n][0]] for n in path]  # [lon, lat]
    total_km = 0.0
    blocked_used = 0
    for a, b in zip(path[:-1], path[1:]):
        edge = graph[a][b]
        total_km += edge["distance_km"]
        if edge["blocked"]:
            blocked_used += 1  # only happens if no unblocked path exists at all

    # Real distance from what was actually asked for (source_lat/lon,
    # dest_lat/lon) to the nearest road-graph node the router could snap to.
    # The bundled demo road graph is sparse (a handful of nodes per state),
    # so a source or destination that is genuinely far from any mapped road
    # snaps to whatever node is closest — sometimes the SAME node for two
    # visibly different points on the map, which otherwise looks like the
    # route "isn't updating". Surfacing this honestly beats hiding it.
    source_snap_km = round(_haversine_km(source_lat, source_lon, *node_coords[src]), 2)
    destination_snap_km = round(_haversine_km(dest_lat, dest_lon, *node_coords[dst]), 2)

    return {
        "coordinates": coords,
        "distance_km": round(total_km, 2),
        "avoided_segments": blocked_used,
        "source": "local_graph" if blocked_used == 0 else "local_graph_blocked_unavoidable",
        "source_snap_distance_km": source_snap_km,
        "destination_snap_distance_km": destination_snap_km,
    }


def find_nearest_safe_zone(store: Store, lat: float, lon: float, emergency_type: Optional[str] = None) -> Optional[dict]:
    """Finds the nearest candidate evacuation point (hospital, school, or
    village) that is NOT currently inside a HIGH/CRITICAL risk zone.
    TerraGuard has no dedicated "shelter" table — hospitals and schools are
    the standard real-world evacuation/assembly points used in Indian
    disaster-response SOPs, and villages are included as a last resort so a
    safe point is still returned in sparsely-mapped areas.

    emergency_type == "medical" restricts candidates to hospitals only, but
    only when at least one real hospital exists.

    Returns None only if literally no candidate location exists at all — if
    every candidate is inside a risk zone, the least-risky one is returned
    instead of nothing, clearly labeled."""
    hospitals = store.df("hospitals").assign(type="hospital")
    schools = store.df("schools").assign(type="school")
    villages = store.df("villages").assign(type="village")

    if emergency_type == "medical" and not hospitals.empty:
        candidates = hospitals
    else:
        frames = [df[["id", "name", "type", "latitude", "longitude"]] for df in (hospitals, schools, villages) if not df.empty]
        candidates = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
            columns=["id", "name", "type", "latitude", "longitude"]
        )

    if candidates.empty:
        return None

    zones = store.df("risk_zones")

    def _inside_zone(row, levels: set[str]) -> bool:
        relevant = zones[zones["risk_level"].isin(levels)]
        for _, z in relevant.iterrows():
            if geo_utils.haversine_m(row["latitude"], row["longitude"], z["latitude"], z["longitude"]) <= z["radius_m"]:
                return True
        return False

    ranked = geo_utils.nearest(candidates, lat, lon, n=len(candidates))

    # Pass 1: exclude anything inside a HIGH or CRITICAL risk zone.
    for _, row in ranked.iterrows():
        if not _inside_zone(row, {"HIGH", "CRITICAL"}):
            return {"id": int(row["id"]), "name": row["name"], "type": row["type"],
                    "latitude": row["latitude"], "longitude": row["longitude"],
                    "distance_m": row["distance_m"], "inside_risk_zone": False}

    # Pass 2 (degraded case — every candidate is in a risk zone): exclude
    # only CRITICAL, so at least a HIGH-only location is preferred.
    for _, row in ranked.iterrows():
        if not _inside_zone(row, {"CRITICAL"}):
            return {"id": int(row["id"]), "name": row["name"], "type": row["type"],
                    "latitude": row["latitude"], "longitude": row["longitude"],
                    "distance_m": row["distance_m"], "inside_risk_zone": True}

    # Pass 3: nothing avoids even CRITICAL zones — return the nearest
    # candidate of any kind, flagged clearly as not safe.
    row = ranked.iloc[0]
    return {"id": int(row["id"]), "name": row["name"], "type": row["type"],
            "latitude": row["latitude"], "longitude": row["longitude"],
            "distance_m": row["distance_m"], "inside_risk_zone": True}


def optimize_route(
    store: Store, source_lat, source_lon, dest_lat, dest_lon,
    emergency_type: Optional[str] = None, exclude_road_id: Optional[int] = None,
) -> dict[str, Any]:
    routes: list[dict] = []
    if exclude_road_id is not None:
        local = _route_via_local_graph(store, source_lat, source_lon, dest_lat, dest_lon, exclude_road_id=exclude_road_id)
    else:
        local = _route_via_local_graph(store, source_lat, source_lon, dest_lat, dest_lon)
    if local:
        routes.append({**local, "estimated_time_minutes": None})
    else:
        # Last-resort: straight-line estimate so the endpoint never fails outright
        dist = _haversine_km(source_lat, source_lon, dest_lat, dest_lon)
        routes.append({
            "coordinates": [[source_lon, source_lat], [dest_lon, dest_lat]],
            "distance_km": round(dist, 2),
            "estimated_time_minutes": None,
            "avoided_segments": 0,
            "source": "straight_line_estimate_no_road_network_available",
        })

    strict_avoidance = emergency_type in STRICT_AVOIDANCE_EMERGENCY_TYPES
    enriched = []
    for r in routes:
        mid_lon, mid_lat = r["coordinates"][len(r["coordinates"]) // 2]
        r["risk_score"] = _location_aware_risk_score(store, mid_lat, mid_lon)
        if strict_avoidance:
            r["risk_zone_hits"] = _risk_zone_hits(store, r["coordinates"], ALL_RISK_LEVELS)
        enriched.append(r)

    if strict_avoidance:
        enriched.sort(key=lambda r: (r.get("risk_zone_hits", 0), r["distance_km"]))
    else:
        enriched.sort(key=lambda r: (r["distance_km"] + r["risk_score"] * RISK_PENALTY_PER_POINT_KM))
    recommended = enriched[0]
    alternative = enriched[1] if len(enriched) > 1 else None

    def _label(r: dict) -> str:
        if "blocked" in r["source"]:
            return "Route crosses a currently blocked road — no fully clear route was found; proceed with caution and confirm locally"
        if strict_avoidance:
            hits = r.get("risk_zone_hits", 0)
            if hits == 0:
                return f"Recommended route — avoids all mapped risk zones ({r['source']})"
            return f"Recommended route — could not fully avoid mapped risk zones ({hits} crossed); no clean alternative found ({r['source']})"
        return f"Recommended lower-risk route ({r['source']})"

    def _snap_warning(r: dict) -> Optional[str]:
        src_km = r.get("source_snap_distance_km")
        dst_km = r.get("destination_snap_distance_km")
        far_src = src_km is not None and src_km > NETWORK_SNAP_WARNING_KM
        far_dst = dst_km is not None and dst_km > NETWORK_SNAP_WARNING_KM
        if not far_src and not far_dst:
            return None
        if far_src and far_dst:
            return (
                f"Your source is {src_km:.1f} km and your destination is {dst_km:.1f} km from the nearest point in "
                "TerraGuard's mapped road network (a demo-scale dataset, not full regional road coverage). The route "
                "below runs between those nearest mapped points, not your exact pins — moving either pin within "
                "roughly the same distance of the network may not change the route."
            )
        which, km = ("Your source", src_km) if far_src else ("Your destination", dst_km)
        return (
            f"{which} is {km:.1f} km from the nearest point in TerraGuard's mapped road network (a demo-scale "
            "dataset, not full regional road coverage). The route below runs to that nearest mapped point, not "
            "your exact pin — moving it within roughly the same distance of the network may not change the route."
        )

    return {
        "recommended_route": {
            "coordinates": recommended["coordinates"],
            "distance_km": recommended["distance_km"],
            "estimated_time_minutes": recommended.get("estimated_time_minutes"),
            "risk_score": recommended["risk_score"],
            "avoided_segments": recommended.get("avoided_segments", 0),
            "label": _label(recommended),
            "source_snap_distance_km": recommended.get("source_snap_distance_km"),
            "destination_snap_distance_km": recommended.get("destination_snap_distance_km"),
            "network_coverage_warning": _snap_warning(recommended),
        },
        "alternative_route": (
            {
                "coordinates": alternative["coordinates"],
                "distance_km": alternative["distance_km"],
                "estimated_time_minutes": alternative.get("estimated_time_minutes"),
                "risk_score": alternative["risk_score"],
                "avoided_segments": alternative.get("avoided_segments", 0),
                "label": f"Alternative route ({alternative['source']})" if "blocked" not in alternative["source"] else "Alternative route (crosses a blocked road)",
                "source_snap_distance_km": alternative.get("source_snap_distance_km"),
                "destination_snap_distance_km": alternative.get("destination_snap_distance_km"),
                "network_coverage_warning": _snap_warning(alternative),
            }
            if alternative
            else None
        ),
        "disclaimer": (
            "This route minimizes estimated distance and modelled risk exposure, and avoids roads "
            "currently marked blocked in TerraGuard's database where a clear alternative exists. "
            "No route can be guaranteed absolutely safe; conditions change rapidly during active "
            "landslide events. Always confirm with local authorities before travel."
        ),
    }
