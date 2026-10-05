import uuid


def test_submit_and_list_report(client):
    resp = client.post(
        "/reports",
        data={
            "latitude": "25.17", "longitude": "93.02", "incident_type": "crack",
            "description": "pytest crack report", "severity": "moderate",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_type"] == "crack"
    assert body["sync_status"] == "synced"

    listing = client.get("/reports")
    assert listing.status_code == 200
    assert any(r["id"] == body["id"] for r in listing.json())


def test_submit_invalid_incident_type_rejected(client):
    resp = client.post(
        "/reports",
        data={"latitude": "25.17", "longitude": "93.02", "incident_type": "not_a_real_type"},
    )
    assert resp.status_code == 422


def test_report_sync_idempotent(client):
    crid = str(uuid.uuid4())
    payload = {
        "reports": [
            {
                "client_report_id": crid, "latitude": 25.0, "longitude": 93.0,
                "incident_type": "debris", "description": "offline queued report", "severity": "high",
            }
        ]
    }
    first = client.post("/reports/sync", json=payload)
    assert first.status_code == 200
    assert first.json()["results"][0]["status"] == "created"

    second = client.post("/reports/sync", json=payload)
    assert second.status_code == 200
    assert second.json()["results"][0]["status"] == "already_synced"
    # idempotent: same server_id both times
    assert first.json()["results"][0]["server_id"] == second.json()["results"][0]["server_id"]
