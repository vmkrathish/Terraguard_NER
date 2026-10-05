def test_rainfall_shock_known_district(client):
    resp = client.get("/rainfall/shock", params={"state": "Assam", "district": "Dima Hasao", "year": 2010, "month": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["daily_data_available"] is False
    assert "note" in body
    assert body["rainfall_month_actual_mm"] is not None  # district alias must resolve


def test_rainfall_shock_unknown_district_does_not_crash(client):
    resp = client.get("/rainfall/shock", params={"state": "Assam", "district": "Nonexistent District", "year": 2010, "month": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rainfall_month_actual_mm"] is None
    assert body["shock_detected"] is False


def test_list_rainfall(client):
    resp = client.get("/rainfall", params={"state": "Sikkim"})
    assert resp.status_code == 200
    assert "records" in resp.json()
