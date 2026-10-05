def test_alert_test_endpoint(client):
    resp = client.post(
        "/alerts/test",
        json={"alert_type": "test", "severity": "high", "latitude": 25.17, "longitude": 93.02, "reason": "pytest alert"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["severity"] == "high"
    assert body["status"] == "test"


def test_alerts_listing(client):
    resp = client.get("/alerts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
