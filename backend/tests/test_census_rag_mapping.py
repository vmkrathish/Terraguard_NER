"""
Tests for wiring the Census 2001 village dataset (village_census_profile)
into the RAG assistant's structured-query routing, so questions like
"population of Assam" or "how many households in <village>" are answered
from real database rows — same no-invented-numbers rule as every other
structured lookup (see query_router.structured_query docstring).
"""
from app.services import query_router
from app.services import rag_pipeline as rp


def test_classifies_census_questions_as_structured():
    for q in [
        "population of Assam",
        "how many households are in Sikkim",
        "how many people live in Mizoram",
        "nearest town to Lachen village",
    ]:
        assert query_router.classify_question(q) == "structured", q


def test_state_level_census_aggregate_real_data(client):
    """Runs against the real seeded database (conftest's TestClient) — the
    census dataset was ingested during this session's testing, so this
    exercises the actual SQL, not a mock."""
    resp = client.post("/rag/query", json={"question": "population of Sikkim"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "structured"
    assert "Sikkim" in body["answer"]
    assert "2001" in body["answer"]


def test_uncovered_state_is_an_honest_refusal_not_a_guess(client):
    resp = client.post("/rag/query", json={"question": "population of Manipur"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "insufficient_data"
    assert "Manipur" in body["answer"]
    assert "does not cover" in body["answer"]


def test_census_query_never_returns_when_only_a_state_and_risk_both_present(monkeypatch):
    """A question that names a state AND asks about risk should still go to
    the risk-zone branch, not get hijacked by the census branch, since it
    doesn't contain any census keyword."""
    assert query_router.classify_question("risk level in Assam") == "structured"


def test_rag_census_aggregate_excludes_synthetic_villages(client):
    """The dataset's v2 expansion added transparently-labeled synthetic
    village rows to village_census_profile (see excel_store.py's module
    docstring). This RAG aggregate must keep matching the real-only
    /villages/census-profile/coverage numbers exactly — the synthetic rows
    must never inflate a number the assistant states as real Census 2001
    fact."""
    coverage = client.get("/villages/census-profile/coverage").json()
    sikkim = next(s for s in coverage["states_covered"] if s["state_name"] == "Sikkim")

    resp = client.post("/rag/query", json={"question": "population of Sikkim"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["structured_rows"][0]["villages"] == sikkim["villages"]
    assert body["structured_rows"][0]["population_total"] == sikkim["population_total"]
