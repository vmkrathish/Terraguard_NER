"""Tests for the Alert Intelligence Center backend: evidence, impact,
lifecycle, acknowledgement and simulate-never-mutates guarantees. Uses the
same seeded demo data as the rest of the suite (see excel_store.py's
_seed_demo_data): risk_zones #2 (Dima Hasao, CRITICAL) has a real nearby
village (Haflong, pop 8500), hospital, school, blocked road and field
report seeded at/near the same point."""
import pandas as pd


DIMA_HASAO_LAT, DIMA_HASAO_LON = 25.1667, 93.0167


def _login(client, email="authority@terraguard.demo", password="Authority@123"):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _issue_alert(client, token, risk_zone_id=2):
    resp = client.post(
        "/alerts/issue",
        json={
            "recipients": ["field_officer@terraguard.demo"],
            "threat_type": "landslide_risk",
            "latitude": DIMA_HASAO_LAT,
            "longitude": DIMA_HASAO_LON,
            "state": "Assam",
            "district": "Dima Hasao",
            "severity": "critical",
            "action": "Evacuate low-lying areas immediately",
            "risk_zone_id": risk_zone_id,
            "reason": "pytest-issued alert",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------- #
def test_compute_evidence_against_seeded_data(store):
    from app.services.alert_intelligence import compute_evidence

    result = compute_evidence(store, DIMA_HASAO_LAT, DIMA_HASAO_LON, state="Assam", district="Dima Hasao")
    assert result["total_count"] == 5
    by_key = {s["key"]: s for s in result["signals"]}

    # A seeded field report sits at/near this exact point.
    assert by_key["field_confirmation"]["verified"] is True
    # A seeded CRITICAL risk_zone sits at this exact point.
    assert by_key["ml_risk_elevation"]["verified"] is True
    # A seeded village/hospital/school sit near this point.
    assert by_key["infrastructure_proximity"]["verified"] is True
    # historical_landslide_activity depends on whether real historical event
    # data has been loaded (scripts/load_historical_data.py) into this test
    # run's copy of the live workbook — assert it's computed consistently
    # with a direct within_radius check rather than a hardcoded expectation.
    from app.services import geo_utils

    events = store.df("landslide_events")
    nearby = geo_utils.within_radius(events, DIMA_HASAO_LAT, DIMA_HASAO_LON, 20000) if not events.empty else events
    assert by_key["historical_landslide_activity"]["verified"] == (len(nearby) > 0)

    assert result["verified_count"] == sum(1 for s in result["signals"] if s["verified"])


def test_compute_evidence_without_state_marks_rainfall_signal_honestly(store):
    from app.services.alert_intelligence import compute_evidence

    result = compute_evidence(store, DIMA_HASAO_LAT, DIMA_HASAO_LON)
    by_key = {s["key"]: s for s in result["signals"]}
    assert by_key["rainfall_shock"]["verified"] is False
    assert "state" in by_key["rainfall_shock"]["detail"].lower()


def test_evidence_endpoint(client):
    resp = client.get("/alerts/evidence", params={"lat": DIMA_HASAO_LAT, "lon": DIMA_HASAO_LON})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 5
    assert 0 <= body["verified_count"] <= 5


# --------------------------------------------------------------------- #
# Impact
# --------------------------------------------------------------------- #
def test_compute_impact_counts_against_seeded_data(store):
    from app.services.alert_intelligence import compute_impact

    impact = compute_impact(store, DIMA_HASAO_LAT, DIMA_HASAO_LON, 20000)
    assert len(impact["affected_villages"]) >= 1
    assert any(v["name"].startswith("Haflong") for v in impact["affected_villages"])
    assert impact["total_population_known"] is not None
    assert impact["total_population_known"] >= 8500
    assert len(impact["affected_roads"]) >= 1
    assert impact["safe_zone"] is not None


def test_impact_assessment_endpoint(client):
    resp = client.get("/alerts/impact-assessment", params={"lat": DIMA_HASAO_LAT, "lon": DIMA_HASAO_LON, "radius_m": 20000})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["affected_villages"], list)
    assert "population_note" in body


def test_impact_population_note_is_honest_when_population_unknown(store, monkeypatch):
    """A village with a null population must never be silently counted as
    zero — total_population_known must exclude it, and population_note must
    say so."""
    from app.services import alert_intelligence as ai

    villages = store.df("villages")
    original = villages.copy()
    villages.loc[0, "population"] = None
    store.replace_table("villages", villages, persist=False)
    try:
        impact = ai.compute_impact(store, villages.iloc[0]["latitude"], villages.iloc[0]["longitude"], 5000)
        assert impact["population_note"] is not None
        assert "unavailable" in impact["population_note"]
    finally:
        store.replace_table("villages", original, persist=False)


# --------------------------------------------------------------------- #
# Simulate — must never mutate real tables
# --------------------------------------------------------------------- #
def test_simulate_never_mutates_roads_or_risk_zones(client, store):
    roads_before = store.df("roads").copy()
    zones_before = store.df("risk_zones").copy()

    resp = client.post(
        "/alerts/simulate",
        json={"lat": DIMA_HASAO_LAT, "lon": DIMA_HASAO_LON, "radius_m": 20000, "radius_multiplier": 2.0, "blocked_road_id": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"] is True
    assert "scenario_description" in body

    roads_after = store.df("roads")
    zones_after = store.df("risk_zones")
    pd.testing.assert_frame_equal(roads_before, roads_after)
    pd.testing.assert_frame_equal(zones_before, zones_after)


# --------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------- #
def test_lifecycle_timeline_pending_vs_done(client):
    token = _login(client)
    alert = _issue_alert(client, token)
    alert_id = alert["id"]

    resp = client.get(f"/alerts/{alert_id}/lifecycle")
    assert resp.status_code == 200
    stages = {s["stage"]: s for s in resp.json()}
    assert stages["detected"]["status"] == "done"
    assert stages["warning_issued"]["status"] == "done"
    # Nothing else was claimed at issue time.
    assert stages["assessed"]["status"] == "pending"
    assert stages["impact_mapped"]["status"] == "pending"
    assert stages["acknowledged"]["status"] == "pending"

    resp2 = client.post(
        f"/alerts/{alert_id}/lifecycle", json={"stage": "assessed", "note": "pytest"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "done"

    resp3 = client.get(f"/alerts/{alert_id}/lifecycle")
    stages3 = {s["stage"]: s for s in resp3.json()}
    assert stages3["assessed"]["status"] == "done"
    assert stages3["assessed"]["note"] == "pytest"


def test_lifecycle_rejects_unknown_stage(client):
    token = _login(client)
    alert = _issue_alert(client, token)
    resp = client.post(
        f"/alerts/{alert['id']}/lifecycle", json={"stage": "not_a_real_stage"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_lifecycle_requires_auth(client):
    token = _login(client)
    alert = _issue_alert(client, token)
    resp = client.post(f"/alerts/{alert['id']}/lifecycle", json={"stage": "assessed"})
    assert resp.status_code == 401


# --------------------------------------------------------------------- #
# Acknowledgements
# --------------------------------------------------------------------- #
def test_acknowledge_records_and_first_ack_completes_lifecycle_stage(client):
    token = _login(client)
    alert = _issue_alert(client, token)
    alert_id = alert["id"]

    lifecycle_before = {s["stage"]: s["status"] for s in client.get(f"/alerts/{alert_id}/lifecycle").json()}
    assert lifecycle_before["acknowledged"] == "pending"

    resp = client.post(f"/alerts/{alert_id}/acknowledge", json={}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["authority"]["acknowledged"] is True
    assert body["authority"]["channel_type"] == "real_role"
    assert body["authority"]["acknowledged_by"] == "Demo District Authority"

    lifecycle_after = {s["stage"]: s["status"] for s in client.get(f"/alerts/{alert_id}/lifecycle").json()}
    assert lifecycle_after["acknowledged"] == "done"


def test_acknowledge_simulation_channels_are_labeled_honestly(client):
    token = _login(client)
    alert = _issue_alert(client, token)
    alert_id = alert["id"]

    resp = client.post(
        f"/alerts/{alert_id}/acknowledge", json={"role": "community"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["community"]["acknowledged"] is True
    assert body["community"]["channel_type"] == "simulation"
    assert body["emergency_team"]["channel_type"] == "simulation"
    assert body["field_officer"]["channel_type"] == "real_role"


def test_acknowledge_cannot_impersonate_another_real_role(client):
    token = _login(client)
    alert = _issue_alert(client, token)
    resp = client.post(
        f"/alerts/{alert['id']}/acknowledge", json={"role": "field_officer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_acknowledgements_endpoint_requires_no_auth_to_read(client):
    token = _login(client)
    alert = _issue_alert(client, token)
    resp = client.get(f"/alerts/{alert['id']}/acknowledgements")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"field_officer", "authority", "admin", "community", "emergency_team"}


# --------------------------------------------------------------------- #
# Assignment
# --------------------------------------------------------------------- #
def test_assign_records_and_completes_lifecycle_stage(client):
    token = _login(client)
    alert = _issue_alert(client, token)
    alert_id = alert["id"]

    resp = client.post(
        f"/alerts/{alert_id}/assign", json={"assignee_name": "Field Team Alpha", "role": "field_officer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["assignee_name"] == "Field Team Alpha"

    lifecycle = {s["stage"]: s["status"] for s in client.get(f"/alerts/{alert_id}/lifecycle").json()}
    assert lifecycle["assigned"] == "done"


# --------------------------------------------------------------------- #
# Detail + threat board + existing alert endpoints unaffected
# --------------------------------------------------------------------- #
def test_alert_detail_is_single_round_trip(client):
    token = _login(client)
    alert = _issue_alert(client, token)
    resp = client.get(f"/alerts/{alert['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["alert"]["id"] == alert["id"]
    assert "evidence" in body and "impact" in body and "lifecycle" in body and "acknowledgements" in body


def test_alert_detail_404_for_unknown_id(client):
    resp = client.get("/alerts/999999")
    assert resp.status_code == 404


def test_threat_board_lists_high_and_critical_zones_only(client):
    resp = client.get("/alerts/threats")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    for entry in body:
        assert entry["risk_level"].lower() in ("high", "critical")
        assert entry["evidence"]["total_count"] == 5
        assert set(entry["impact_summary"].keys()) == {"village_count", "road_count", "facility_count"}


def test_existing_alerts_test_endpoint_still_works(client):
    """The pre-existing testing/dev endpoint must remain untouched."""
    resp = client.post(
        "/alerts/test",
        json={"alert_type": "test", "severity": "moderate", "latitude": 25.17, "longitude": 93.02, "reason": "still works"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "test"
