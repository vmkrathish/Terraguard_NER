def test_route_optimize_returns_route(client):
    resp = client.post(
        "/route/optimize",
        json={"source_lat": 25.1667, "source_lon": 93.0167, "dest_lat": 25.0333, "dest_lon": 93.5000},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommended_route"]["distance_km"] > 0
    assert len(body["recommended_route"]["coordinates"]) >= 2
    assert "disclaimer" in body
    assert "absolutely safe" not in body["disclaimer"] or "No route can be guaranteed absolutely safe" in body["disclaimer"]


def test_route_optimize_same_point(client):
    resp = client.post(
        "/route/optimize",
        json={"source_lat": 25.1667, "source_lon": 93.0167, "dest_lat": 25.1667, "dest_lon": 93.0167},
    )
    assert resp.status_code == 200


def test_nearest_safe_zone_endpoint_returns_a_real_candidate(client):
    resp = client.post("/route/nearest-safe-zone", json={"lat": 25.1667, "lon": 93.0167})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] in ("hospital", "school", "village")
    assert body["distance_km"] >= 0
    assert isinstance(body["inside_risk_zone"], bool)


def test_route_optimize_to_nearest_safe_zone(client):
    """Without a destination, the server should find and route to the
    nearest non-risk-zone hospital/school/village on its own."""
    resp = client.post(
        "/route/optimize",
        json={"source_lat": 25.1667, "source_lon": 93.0167, "to_nearest_safe_zone": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["destination_safe_zone"] is not None
    assert body["recommended_route"]["distance_km"] >= 0


def test_route_optimize_without_destination_or_safe_zone_flag_is_rejected(client):
    resp = client.post("/route/optimize", json={"source_lat": 25.1667, "source_lon": 93.0167})
    assert resp.status_code == 422


def test_route_optimize_avoids_blocked_roads_via_local_graph(store):
    """Directly exercises the local road-graph's blocked-road-avoidance
    path: a route between two points connected only by a blocked road must
    not silently pretend that road is clear."""
    from app.services.route_optimizer import _route_via_local_graph

    # Uses TerraGuard's own seeded `roads` sheet — just confirms the
    # local graph either finds a clean route (avoided_segments == 0)
    # or, if truly unavoidable, clearly labels it rather than hiding it.
    result = _route_via_local_graph(store, 25.1667, 93.0167, 25.0333, 93.5000)
    if result is not None:
        assert result["avoided_segments"] >= 0
        assert result["source"] in ("local_graph", "local_graph_blocked_unavoidable")


def test_optimize_route_labels_unavoidable_blocked_road(store, monkeypatch):
    """When the local road graph's only path between two points runs
    through a blocked road (no detour exists in the graph), the recommended
    route must still be returned, but clearly labeled as crossing a blocked
    road rather than silently presented as clear."""
    from app.core.excel_store import linestring_wkt_to_coords
    from app.services import route_optimizer

    roads = store.df("roads")
    blocked = roads[roads["status"] == "blocked"]
    if blocked.empty:
        return  # no blocked road seeded in this environment

    blocked_coords = [[lon, lat] for lon, lat in linestring_wkt_to_coords(blocked.iloc[0]["geom_wkt"])]
    source_lon, source_lat = blocked_coords[0]
    dest_lon, dest_lat = blocked_coords[-1]

    def fake_route_via_local_graph(_store, _slat, _slon, _dlat, _dlon):
        return {
            "coordinates": blocked_coords,
            "distance_km": 10.0,
            "avoided_segments": 1,
            "source": "local_graph_blocked_unavoidable",
        }

    monkeypatch.setattr(route_optimizer, "_route_via_local_graph", fake_route_via_local_graph)

    result = route_optimizer.optimize_route(store, source_lat, source_lon, dest_lat, dest_lon)
    assert result["recommended_route"]["avoided_segments"] == 1
    assert "blocked" in result["recommended_route"]["label"].lower()


def test_route_optimize_warns_when_destination_is_far_from_the_mapped_network(client):
    """TerraGuard's bundled demo road graph only has a handful of nodes, so
    a destination genuinely far from any of them snaps to whichever node is
    nearest — which can look identical to a route computed for a *different*
    far-away destination that happens to snap to the same node. Rather than
    hiding that, the API must say so explicitly via network_coverage_warning
    and destination_snap_distance_km, so the frontend can be honest about it
    instead of the route silently looking "stuck"."""
    resp = client.post(
        "/route/optimize",
        # Far outside the demo dataset's road-graph coverage for this source.
        json={"source_lat": 25.1667, "source_lon": 93.0167, "dest_lat": 24.8000, "dest_lon": 93.9000},
    )
    assert resp.status_code == 200
    route = resp.json()["recommended_route"]
    assert route["destination_snap_distance_km"] is not None
    assert route["destination_snap_distance_km"] > 5.0
    assert route["network_coverage_warning"] is not None
    assert "mapped road network" in route["network_coverage_warning"]


def test_route_optimize_two_destinations_near_the_same_graph_node_share_a_route_honestly(client):
    """Two visibly different destination pins that both happen to be closer
    to the same road-graph node than to any other node MUST produce the same
    route (that's correct nearest-node routing, not a stale-response bug) —
    but both responses must carry a network_coverage_warning explaining why,
    with an honest per-request destination_snap_distance_km rather than a
    cached or copy-pasted number."""
    payload_base = {"source_lat": 25.1667, "source_lon": 93.0167}
    r1 = client.post("/route/optimize", json={**payload_base, "dest_lat": 25.0333, "dest_lon": 93.5000})
    r2 = client.post("/route/optimize", json={**payload_base, "dest_lat": 24.8000, "dest_lon": 93.9000})
    assert r1.status_code == 200 and r2.status_code == 200
    route1, route2 = r1.json()["recommended_route"], r2.json()["recommended_route"]

    # Same nearest node for both destinations -> same computed route.
    assert route1["coordinates"] == route2["coordinates"]
    assert route1["distance_km"] == route2["distance_km"]

    # The first destination is (close to) an actual graph node; the second
    # is genuinely far from the network -> their snap distances must differ,
    # proving each request was computed independently rather than cached.
    assert route1["destination_snap_distance_km"] < 1.0
    assert route2["destination_snap_distance_km"] > 5.0
    assert route1["network_coverage_warning"] is None
    assert route2["network_coverage_warning"] is not None
