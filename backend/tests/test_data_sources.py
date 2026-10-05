"""Tests for the data_sources adapter/orchestrator package.

Adapter-parsing tests (NASA POWER / SoilGrids response handling) are pure
unit tests against an injected fake httpx client — no real network call, no
database. Orchestrator tests use the real database (like the rest of this
suite's API tests) to verify genuine caching/fallback behavior, not mocks
of SQLAlchemy itself.
"""
import httpx
import pytest

from app.services.data_sources.nasa_power_adapter import NasaPowerAdapter
from app.services.data_sources.soilgrids_adapter import SoilGridsAdapter
from app.services.data_sources.provenance import AdapterUnavailable, DataKind
from app.services.data_sources.validators import is_plausible, validate_record_values


class _FakeTransport(httpx.BaseTransport):
    def __init__(self, body: dict):
        self.body = body

    def handle_request(self, request):
        return httpx.Response(200, json=self.body)


def test_nasa_power_parses_real_response_shape_and_ignores_fill_value():
    body = {"properties": {"parameter": {"PRECTOTCORR": {
        "20260910": 12.3, "20260911": 5.4, "20260912": -999,
    }}}}
    adapter = NasaPowerAdapter(http_client=httpx.Client(transport=_FakeTransport(body)))
    record = adapter.fetch(25.57, 92.7)
    assert record.data_kind == DataKind.REANALYSIS
    assert record.is_live is False
    # -999 (NASA POWER's own documented fill value) must be excluded, not
    # treated as zero rainfall.
    assert record.values["window_days"] == 2
    assert record.values["rainfall_mm_day_latest"] == 5.4
    assert record.values["rainfall_mm_total_window"] == pytest.approx(17.7)


def test_nasa_power_raises_adapter_unavailable_on_bad_shape():
    adapter = NasaPowerAdapter(http_client=httpx.Client(transport=_FakeTransport({"unexpected": True})))
    with pytest.raises(AdapterUnavailable):
        adapter.fetch(25.57, 92.7)


def test_nasa_power_raises_when_all_values_are_fill_value():
    body = {"properties": {"parameter": {"PRECTOTCORR": {"20260910": -999}}}}
    adapter = NasaPowerAdapter(http_client=httpx.Client(transport=_FakeTransport(body)))
    with pytest.raises(AdapterUnavailable):
        adapter.fetch(25.57, 92.7)


def test_soilgrids_parses_real_response_shape_and_applies_unit_conversion():
    body = {"properties": {"layers": [
        {"name": "clay", "depths": [{"label": "0-5cm", "values": {"mean": 210}}]},
        {"name": "soc", "depths": [{"label": "0-5cm", "values": {"mean": 145}}]},
    ]}}
    adapter = SoilGridsAdapter(http_client=httpx.Client(transport=_FakeTransport(body)))
    record = adapter.fetch(25.57, 92.7)
    assert record.data_kind == DataKind.STATIC_SOIL_PROPERTY
    assert record.values["clay_pct"] == 21.0
    assert record.values["soil_organic_carbon_g_kg"] == 14.5
    assert record.normalized_units["clay_pct"] == "%"


def test_soilgrids_raises_adapter_unavailable_when_no_layers_match():
    body = {"properties": {"layers": [{"name": "unknown_property", "depths": []}]}}
    adapter = SoilGridsAdapter(http_client=httpx.Client(transport=_FakeTransport(body)))
    with pytest.raises(AdapterUnavailable):
        adapter.fetch(25.57, 92.7)


def test_validator_rejects_implausible_rainfall_but_keeps_plausible_fields():
    accepted, rejected = validate_record_values({"rainfall_mm_day": 9999.0, "window_days": 3})
    assert "rainfall_mm_day" in rejected
    assert accepted == {"window_days": 3}  # unrecognized field name passes through (no declared range)


def test_validator_plausibility_ranges():
    assert is_plausible("clay_pct", 45.0) is True
    assert is_plausible("clay_pct", 150.0) is False
    assert is_plausible("clay_pct", None) is False


def test_orchestrator_returns_insufficient_data_when_every_adapter_fails(client, store, monkeypatch):
    from app.services.data_sources import registry as reg
    from app.services.data_sources.orchestrator import get_current_rainfall
    from app.services.data_sources.provenance import AdapterUnavailable

    class _AlwaysFails:
        key = "nasa_power"

        def is_configured(self):
            return True

        def fetch(self, lat, lon, **kw):
            raise AdapterUnavailable("simulated outage")

    monkeypatch.setitem(reg._REGISTRY, "nasa_power", _AlwaysFails())
    monkeypatch.setitem(reg._REGISTRY, "imd", _AlwaysFails())

    # A coordinate far outside anywhere previously exercised, so this
    # test doesn't depend on cache state left by other tests/runs.
    result = get_current_rainfall(store, 1.234, 5.678)
    assert result["status"] == "insufficient_data"
    assert "insufficient" in result["message"].lower() or "no current rainfall" in result["message"].lower()


def test_data_sources_status_endpoint_reports_every_adapter(client):
    resp = client.get("/data-sources/status")
    assert resp.status_code == 200
    keys = {a["source"] for a in resp.json()["adapters"]}
    assert {"nasa_power", "soilgrids", "imd", "copernicus", "bhuvan", "osm", "usgs"} <= keys
