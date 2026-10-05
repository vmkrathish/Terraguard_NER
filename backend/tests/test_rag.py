def test_rag_query_no_llm_falls_back_gracefully(client):
    """With no LLM_PROVIDER configured (the default), the endpoint must
    never crash and must clearly indicate the fallback."""
    resp = client.post("/rag/query", json={"question": "What should authorities do at critical risk?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_used"] is False
    assert body["fallback_reason"] is not None


def test_rag_query_nonsense_question_reports_no_source(client):
    resp = client.post("/rag/query", json={"question": "zzzz qqqq unrelated nonsense xyzzy"})
    assert resp.status_code == 200
    body = resp.json()
    # either graceful "no adequate source" or a low-similarity fallback answer — never a 500
    assert "answer" in body


def test_rag_ingest_endpoint_runs(client):
    resp = client.post("/rag/ingest")
    assert resp.status_code == 200
    body = resp.json()
    assert "documents_ingested" in body


def test_rag_reembed_endpoint_runs(client):
    resp = client.post("/rag/reembed")
    assert resp.status_code == 200
    body = resp.json()
    assert "chunks_reembedded" in body
    assert "backend" in body


def test_rag_query_structured_question_never_invents_numbers(client):
    """A structured question ('highest risk area') must be answered from a
    real database row, never an LLM guess — answer_type must say so."""
    resp = client.post("/rag/query", json={"question": "Which area has the highest risk?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "structured"
    assert len(body["structured_rows"]) > 0
    # No LLM is configured in tests, so the raw computed summary is returned verbatim.
    assert body["llm_used"] is False


def test_rag_query_no_data_available_says_so_clearly(client):
    """A structured-shaped question TerraGuard genuinely has no data for
    (slope angle isn't tracked) must say so plainly, not guess a value."""
    resp = client.post("/rag/query", json={"question": "What is the slope angle of this location?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "insufficient_data"
    assert "does not currently store slope" in body["answer"] or "not tracked" in body["answer"].lower()


def test_rag_query_landslide_history_is_a_real_count(client):
    resp = client.post("/rag/query", json={"question": "How many landslides happened in Assam?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] == "structured"
    assert "Assam" in body["answer"]
