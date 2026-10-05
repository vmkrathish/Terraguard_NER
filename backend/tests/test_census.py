"""Integration tests for the village census profile API. These hit the
real database like the other API tests in this suite (test_rainfall.py,
test_landslides_and_map.py, etc.) — they require
scripts/ingest_village_census.py to have been run first (see
docs/DATASET_SCHEMA_DIFF.md for the exact commands). If the table is empty,
the "no data" tests still pass but the "has data" tests are skipped rather
than failing, since an empty table is a valid (if unhelpful) state for a
fresh database that hasn't imported the dataset yet.
"""
import pytest


def _has_any_census_rows(client) -> bool:
    resp = client.get("/villages/census-profile/coverage")
    if resp.status_code != 200:
        return False
    return sum(s["villages"] for s in resp.json()["states_covered"]) > 0


def test_census_profile_coverage_lists_manipur_as_not_covered(client):
    resp = client.get("/villages/census-profile/coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert "Manipur" in body["states_not_covered"]
    assert body["has_coordinates"] is False
    assert body["used_for_ml_features"] is False
    assert "slope_percent" in body["fields_never_available_in_this_dataset"]


def test_census_profile_unmatched_query_says_so_clearly_not_invented(client):
    resp = client.get("/villages/census-profile", params={"village_name": "ZzNoSuchVillageZz"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] == 0
    assert body["results"] == []
    assert body["note"] is not None


def test_census_profile_state_filter_returns_only_that_state(client):
    if not _has_any_census_rows(client):
        pytest.skip("village_census_profile is empty — run scripts/ingest_village_census.py first")
    resp = client.get("/villages/census-profile", params={"state": "Assam", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] > 0
    for row in body["results"]:
        assert row["state_name"] == "Assam"
        # Never fabricated: geotechnical fields must be None (dataset has none)
        assert row["slope_percent"] is None
        assert row["elevation_m"] is None


def test_census_profile_never_exposes_a_geometry_or_lat_lon_field(client):
    # This dataset genuinely has no coordinates — the response model must
    # never claim to have latitude/longitude for it.
    resp = client.get("/villages/census-profile", params={"state": "Sikkim", "limit": 1})
    assert resp.status_code == 200
    for row in resp.json()["results"]:
        assert "latitude" not in row
        assert "longitude" not in row


# --- Tests for the dataset's v2 expansion (real + transparently-labeled
# synthetic rows) — see excel_store.py's module docstring for the full
# provenance convention these exercise. ---------------------------------


def test_census_profile_excludes_synthetic_rows_by_default(client):
    if not _has_any_census_rows(client):
        pytest.skip("village_census_profile is empty — run scripts/ingest_village_census.py first")
    resp = client.get("/villages/census-profile", params={"village_name": "Synthetic_Village", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] == 0
    assert body["query"]["include_synthetic"] is False


def test_census_profile_include_synthetic_returns_clearly_labeled_rows(client):
    if not _has_any_census_rows(client):
        pytest.skip("village_census_profile is empty — run scripts/ingest_village_census.py first")
    resp = client.get(
        "/villages/census-profile",
        params={"village_name": "Synthetic_Village", "include_synthetic": "true", "limit": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    if body["matched"] == 0:
        pytest.skip("dataset has no synthetic rows loaded")
    for row in body["results"]:
        assert row["data_provenance"] == "synthetic_generated_v1"
        assert row["quality_status"] == "synthetic_not_verified_statistical_model"


def test_census_profile_real_rows_still_labeled_historical_verified(client):
    # Unchanged behavior for every real row, before or after the v2 dataset
    # expansion — a real Census-2001 row must never pick up the synthetic
    # label just because synthetic rows now exist in the same table.
    if not _has_any_census_rows(client):
        pytest.skip("village_census_profile is empty — run scripts/ingest_village_census.py first")
    resp = client.get("/villages/census-profile", params={"state": "Assam", "limit": 3})
    assert resp.status_code == 200
    for row in resp.json()["results"]:
        assert row["data_provenance"] == "historical"
        assert row["quality_status"] == "verified"


def test_census_profile_coverage_reports_synthetic_count_separately(client):
    resp = client.get("/villages/census-profile/coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert "synthetic_villages_available" in body
    assert isinstance(body["synthetic_villages_available"], int)
    # Real per-state counts must stay exactly what they were before the v2
    # expansion — the synthetic rows must never inflate them.
    real_total = sum(s["villages"] for s in body["states_covered"])
    if body["synthetic_villages_available"] > 0:
        assert body["synthetic_villages_note"] is not None
        # A real dataset the size of this project's should have meaningfully
        # more real villages than a coincidental off-by-one would produce.
        assert real_total > 1000
