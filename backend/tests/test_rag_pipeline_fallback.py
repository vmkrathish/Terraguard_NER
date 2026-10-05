"""
Unit tests for rag_pipeline._document_answer's LLM-failure handling.

These monkeypatch rag_pipeline's own module-level functions (similarity
search, LLM calls) rather than hitting a real database or a real LLM
provider, so they run offline and verify the actual fallback-ordering logic:
when the in-context explanation attempt fails, the SAME configured
multi-provider chain's general-knowledge path must be tried before ever
falling back to a raw, unexplained dump of retrieved chunks — and that raw
dump, on the rare occasion it is reached, must not falsely claim "No LLM
configured" when one actually was.
"""
import pytest

from app.services import rag_pipeline as rp
from app.services.llm_providers import LLMUnavailable


class _FakeDB:
    """rag_pipeline._document_answer never touches `db` directly — every
    call that would (similarity_search) is monkeypatched below — so a
    placeholder object is enough; no real database connection is needed."""


def _fake_results(n=1, similarity=0.5):
    return [
        {
            "content": f"Real TerraGuard source content #{i}",
            "chunk_index": i,
            "metadata": {},
            "title": "some_doc.md",
            "source": "knowledge_base",
            "similarity": similarity,
        }
        for i in range(n)
    ]


def test_document_answer_retries_general_knowledge_when_explain_call_fails(monkeypatch):
    """The in-context explanation attempt raises LLMUnavailable even though
    adequate sources were found; _document_answer must retry through
    _general_knowledge_answer (the SAME configured chain) rather than
    immediately dumping raw excerpts."""
    monkeypatch.setattr(rp, "similarity_search", lambda db, q, k: _fake_results())
    monkeypatch.setattr(rp, "_min_adequate_similarity", lambda: 0.3)
    monkeypatch.setattr(rp, "is_llm_configured", lambda: True)

    def fail(*args, **kwargs):
        raise LLMUnavailable("all configured providers failed evaluation: groq: request_failed (500)")

    monkeypatch.setattr(rp, "generate_answer_with_provider_and_comparison", fail)
    monkeypatch.setattr(
        rp,
        "generate_general_knowledge_answer_with_comparison",
        lambda q: ("General guidance: move to higher ground.", "gemini", [{"provider": "gemini", "status": "ok"}]),
    )
    monkeypatch.setattr(rp._settings, "LLM_PROVIDER", "multi")

    result = rp._document_answer(_FakeDB(), "hii", top_k=4)

    assert result["answer_type"] == "general_knowledge"
    assert "move to higher ground" in result["answer"]
    assert "llm_explain_failed_used_general_knowledge" in result["fallback_reason"]
    assert result["llm_comparison"] is not None


def test_document_answer_falls_back_to_labeled_excerpt_dump_when_everything_fails(monkeypatch):
    """When BOTH the in-context explanation AND the general-knowledge retry
    fail (or general knowledge isn't available, e.g. not in 'multi' mode),
    the raw excerpt dump is the true last resort — and it must say the AI
    explanation was unavailable, never the flatly wrong 'No LLM configured'
    when a provider actually was configured."""
    monkeypatch.setattr(rp, "similarity_search", lambda db, q, k: _fake_results())
    monkeypatch.setattr(rp, "_min_adequate_similarity", lambda: 0.3)
    monkeypatch.setattr(rp, "is_llm_configured", lambda: True)

    def fail(*args, **kwargs):
        raise LLMUnavailable("all configured providers failed evaluation")

    monkeypatch.setattr(rp, "generate_answer_with_provider_and_comparison", fail)
    monkeypatch.setattr(rp, "_general_knowledge_answer", lambda q: None)

    result = rp._document_answer(_FakeDB(), "some question", top_k=4)

    assert result["answer_type"] == "document"
    assert "No LLM configured" not in result["answer"]
    assert "AI explanation unavailable right now" in result["answer"]
    assert "Real TerraGuard source content" in result["answer"]


def test_document_answer_raw_dump_says_not_configured_only_when_actually_not_configured(monkeypatch):
    monkeypatch.setattr(rp, "similarity_search", lambda db, q, k: _fake_results())
    monkeypatch.setattr(rp, "_min_adequate_similarity", lambda: 0.3)
    monkeypatch.setattr(rp, "is_llm_configured", lambda: False)

    result = rp._document_answer(_FakeDB(), "some question", top_k=4)

    assert result["answer_type"] == "document"
    assert "No LLM configured — showing retrieved source excerpts directly" in result["answer"]
