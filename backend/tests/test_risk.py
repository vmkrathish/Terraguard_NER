def test_predict_returns_valid_risk_level(client):
    resp = client.post(
        "/risk/predict",
        json={
            "latitude": 25.1667, "longitude": 93.0167, "state": "Assam", "district": "Dima Hasao",
            "observation_month": 6, "observation_year": 2024, "rainfall_month_actual_mm": 450,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 0.0 <= body["probability"] <= 1.0
    assert 0.0 <= body["risk_score"] <= 100.0
    assert body["risk_level"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
    assert body["explainability_method"] in ("shap", "feature_importance_fallback", "unavailable")
    assert "disclaimer" in body


def test_predict_missing_optional_fields_still_works(client):
    resp = client.post("/risk/predict", json={"latitude": 27.17, "longitude": 88.53})
    assert resp.status_code == 200


def test_predict_invalid_latitude_rejected(client):
    resp = client.post("/risk/predict", json={"latitude": 999, "longitude": 88.53})
    assert resp.status_code == 422


def test_risk_level_thresholds_configurable():
    from app.services.risk_engine import risk_level_for_score

    assert risk_level_for_score(0) == "LOW"
    assert risk_level_for_score(24) == "LOW"
    assert risk_level_for_score(25) == "MODERATE"
    assert risk_level_for_score(50) == "HIGH"
    assert risk_level_for_score(75) == "CRITICAL"
    assert risk_level_for_score(100) == "CRITICAL"
