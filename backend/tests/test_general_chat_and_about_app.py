"""
Unit tests for the "general_chat" / "about_app" question types added to fix:
  - "hii" producing a red "No sufficient data found" error instead of a
    casual chatbot reply.
  - "name of this application?" producing a long, slow, rambling raw-context
    dump instead of a short direct answer.

Both new paths must be instant (no DB query, no RAG similarity search, no
LLM call) — that's what makes them fast and always-available regardless of
which LLM_PROVIDER is configured.
"""
from app.services import query_router
from app.services import rag_pipeline as rp


class _FakeDB:
    """Never touched by the general_chat/about_app paths — a placeholder is
    enough since these paths must not query the database at all."""


# --- classification ----------------------------------------------------

def test_classifies_common_greetings_as_general_chat():
    for q in ["hii", "hi", "Hi!", "hello", "hey", "yo", "namaste", "good morning"]:
        assert query_router.classify_question(q) == "general_chat", q


def test_classifies_thanks_bye_ack_as_general_chat():
    for q in ["thanks", "thank you", "ty", "bye", "goodbye", "ok", "okay", "cool"]:
        assert query_router.classify_question(q) == "general_chat", q


def test_classifies_app_identity_questions_as_about_app():
    for q in [
        "name of this application?",
        "what is this app",
        "what's this application",
        "who are you",
        "what can you do",
        "tell me about terraguard",
    ]:
        assert query_router.classify_question(q) == "about_app", q


def test_does_not_misclassify_real_data_questions():
    assert query_router.classify_question("how many landslides occurred in Assam") == "structured"
    assert query_router.classify_question("what are the evacuation steps for flooding") == "document"


# --- answer_query() short-circuits, no DB/LLM call ----------------------

def test_answer_query_general_chat_is_instant_and_never_touches_db_or_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not query the database or call an LLM for a greeting")

    monkeypatch.setattr(rp, "similarity_search", boom)
    monkeypatch.setattr(rp, "generate_answer_with_provider_and_comparison", boom)
    monkeypatch.setattr(query_router, "structured_query", boom)

    result = rp.answer_query(_FakeDB(), "hii", top_k=4)

    assert result["answer_type"] == "general_chat"
    assert result["llm_used"] is False
    assert result["answer"]


def test_answer_query_about_app_is_instant_and_never_touches_db_or_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not query the database or call an LLM for an app-identity question")

    monkeypatch.setattr(rp, "similarity_search", boom)
    monkeypatch.setattr(rp, "generate_answer_with_provider_and_comparison", boom)
    monkeypatch.setattr(query_router, "structured_query", boom)

    result = rp.answer_query(_FakeDB(), "name of this application?", top_k=4)

    assert result["answer_type"] == "about_app"
    assert result["llm_used"] is False
    assert "TerraGuard" in result["answer"]
