def test_list_landslides(client):
    resp = client.get("/landslides", params={"state": "Sikkim", "limit": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    if body:
        assert body[0]["data_provenance"] == "historical"


def test_map_layers(client):
    resp = client.get("/map/layers")
    assert resp.status_code == 200
    body = resp.json()
    for key in ["risk_zones", "landslide_events", "field_reports", "roads", "villages", "hospitals", "schools"]:
        assert key in body
