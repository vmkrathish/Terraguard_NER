"""
Unit tests for the chatbot's LLM provider chain (llm_providers.py).

These never make a real network call — each provider function is
monkeypatched to simulate success, failure, or an ungrounded (hallucinated)
response, so the tests run offline and verify the actual chain/scoring/
groundedness logic rather than any particular provider's live API.

The chat chain is a strict PRIMARY-THEN-FALLBACK sequence: Groq first,
OpenRouter only if Groq fails or is rejected, and Gemini is never called
from the chat path at all (regardless of LLM_PROVIDER_CHAIN or whether
GEMINI_API_KEY is set) — see _chat_chain() in llm_providers.py.
"""
import pytest

from app.services import llm_providers as lp


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    """Every test gets a clean slate: no provider keys set, chain in the
    documented default order, LLM_PROVIDER='multi'."""
    monkeypatch.setattr(lp.settings, "LLM_PROVIDER", "multi")
    monkeypatch.setattr(lp.settings, "LLM_PROVIDER_CHAIN", "groq,gemini,openrouter")
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", None)
    monkeypatch.setattr(lp.settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(lp.settings, "OPENROUTER_API_KEY", None)


def test_configured_chain_skips_providers_with_no_key(monkeypatch):
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(lp.settings, "GEMINI_API_KEY", "test-key")
    assert lp._configured_chain() == ["groq", "gemini"]


def test_configured_chain_empty_when_no_keys_set():
    assert lp._configured_chain() == []


def test_configured_chain_respects_custom_order(monkeypatch):
    monkeypatch.setattr(lp.settings, "LLM_PROVIDER_CHAIN", "openrouter,groq")
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "OPENROUTER_API_KEY", "k")
    assert lp._configured_chain() == ["openrouter", "groq"]


def test_chat_chain_excludes_gemini_even_when_configured_first(monkeypatch):
    """Gemini must never be part of the chat chain, even if it's first in
    LLM_PROVIDER_CHAIN and has a key set."""
    monkeypatch.setattr(lp.settings, "LLM_PROVIDER_CHAIN", "gemini,groq,openrouter")
    monkeypatch.setattr(lp.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "OPENROUTER_API_KEY", "k")
    assert lp._chat_chain() == ["groq", "openrouter"]


def test_chat_chain_is_always_groq_then_openrouter_regardless_of_env_order(monkeypatch):
    """Even if LLM_PROVIDER_CHAIN lists openrouter before groq, the chat
    chain always tries Groq first."""
    monkeypatch.setattr(lp.settings, "LLM_PROVIDER_CHAIN", "openrouter,gemini,groq")
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "GEMINI_API_KEY", "k")
    assert lp._chat_chain() == ["groq", "openrouter"]


def test_chat_chain_empty_when_only_gemini_key_is_set(monkeypatch):
    monkeypatch.setattr(lp.settings, "GEMINI_API_KEY", "k")
    assert lp._chat_chain() == []
    assert lp.is_llm_configured() is False


def test_is_grounded_true_when_answer_reuses_context_numbers():
    context = ["Rainfall in Assam was 450mm in July with 12 recorded events."]
    answer = "Assam recorded 450mm of rainfall and 12 landslide events in July."
    grounded, reason = lp._is_grounded(answer, context)
    assert grounded is True
    assert reason is None


def test_is_grounded_false_when_answer_invents_a_number():
    context = ["Rainfall in Assam was 450mm in July with 12 recorded events."]
    answer = "Assam recorded 999mm of rainfall in July, an unprecedented total."
    grounded, reason = lp._is_grounded(answer, context)
    assert grounded is False
    assert "ungrounded_number" in reason


def test_is_grounded_ignores_single_digit_numbers():
    # Single digits are common in ordinary prose ("step 1", "3 precautions")
    # and would produce constant false positives if checked strictly.
    context = ["Follow evacuation guidance for high-risk zones."]
    answer = "Here are 3 steps to follow: 1) evacuate, 2) alert neighbors."
    grounded, _ = lp._is_grounded(answer, context)
    assert grounded is True


def test_is_grounded_false_on_empty_answer():
    grounded, reason = lp._is_grounded("", ["some context"])
    assert grounded is False
    assert reason == "empty_or_too_short"


def test_score_candidate_rewards_completeness_up_to_cap():
    short_score = lp._score_candidate("Evacuate now.", latency_seconds=1.0)
    full_score = lp._score_candidate("Evacuate now. " * 40, latency_seconds=1.0)
    assert full_score > short_score


def test_score_candidate_rewards_lower_latency_as_tiebreaker():
    fast_score = lp._score_candidate("A reasonably complete answer with real content." * 3, latency_seconds=0.5)
    slow_score = lp._score_candidate("A reasonably complete answer with real content." * 3, latency_seconds=15.0)
    assert fast_score > slow_score


def test_multi_evaluation_raises_when_no_provider_configured():
    with pytest.raises(lp.LLMUnavailable):
        lp.generate_answer_multi("What is the risk?", ["some context with no numbers"])


def test_multi_evaluation_never_calls_gemini_even_if_configured(monkeypatch):
    """Gemini has a key AND would succeed, but it must never be invoked from
    the chat path — only Groq (which fails here) and OpenRouter are ever
    tried."""
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "OPENROUTER_API_KEY", "k")

    gemini_called = {"value": False}

    def fail(*args, **kwargs):
        raise RuntimeError("simulated network failure")

    def gemini_would_succeed(system_prompt, user_prompt):
        gemini_called["value"] = True
        return "Gemini should never be reached."

    def openrouter_succeeds(system_prompt, user_prompt):
        return "The context indicates a moderate risk level."

    monkeypatch.setitem(lp._PROVIDER_FUNCS, "groq", fail)
    monkeypatch.setitem(lp._PROVIDER_FUNCS, "gemini", gemini_would_succeed)
    monkeypatch.setitem(lp._PROVIDER_FUNCS, "openrouter", openrouter_succeeds)

    answer, provider = lp.generate_answer_multi("What is the risk?", ["Context: moderate risk level reported."])
    assert provider == "openrouter"
    assert "moderate risk" in answer
    assert gemini_called["value"] is False


def test_groq_success_means_openrouter_is_not_called(monkeypatch):
    """Test 4 from the optimization brief: Groq succeeds -> its answer is
    returned and OpenRouter is never invoked."""
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "OPENROUTER_API_KEY", "k")

    openrouter_called = {"value": False}

    def groq_succeeds(system_prompt, user_prompt):
        return "There were 12 landslides recorded this season."

    def openrouter_fn(system_prompt, user_prompt):
        openrouter_called["value"] = True
        return "should not be reached"

    monkeypatch.setitem(lp._PROVIDER_FUNCS, "groq", groq_succeeds)
    monkeypatch.setitem(lp._PROVIDER_FUNCS, "openrouter", openrouter_fn)

    answer, provider, comparison = lp.generate_answer_multi_with_comparison(
        "How many landslides?", ["12 landslides were recorded this season."]
    )
    assert provider == "groq"
    assert "12 landslides" in answer
    assert openrouter_called["value"] is False

    statuses = {c["provider"]: c["status"] for c in comparison}
    assert statuses["groq"] == "ok"
    assert statuses["openrouter"] == "not_called"
    groq_entry = next(c for c in comparison if c["provider"] == "groq")
    assert groq_entry["selected_as_optimal"] is True


def test_groq_failure_falls_back_to_openrouter(monkeypatch):
    """Test 5 from the optimization brief: Groq fails -> OpenRouter is
    called and its answer is used."""
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "OPENROUTER_API_KEY", "k")

    def fail(*args, **kwargs):
        raise RuntimeError("simulated network failure")

    def succeed(system_prompt, user_prompt):
        return "The context indicates a moderate risk level."

    monkeypatch.setitem(lp._PROVIDER_FUNCS, "groq", fail)
    monkeypatch.setitem(lp._PROVIDER_FUNCS, "openrouter", succeed)

    answer, provider = lp.generate_answer_multi("What is the risk?", ["Context: moderate risk level reported."])
    assert provider == "openrouter"
    assert "moderate risk" in answer


def test_groq_ungrounded_answer_falls_back_to_openrouter(monkeypatch):
    """Groq returns a longer, fluent, but ungrounded (hallucinated) answer;
    the chain must reject it outright and fall back to OpenRouter's
    grounded answer instead — this is the enforcement point for the
    project's no-fabrication rule when a free-tier LLM is generating text."""
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "OPENROUTER_API_KEY", "k")

    def hallucinate(system_prompt, user_prompt):
        return "There were 9999 landslides recorded this season, an all-time record for the region. " * 3

    def grounded_answer(system_prompt, user_prompt):
        return "There were 12 landslides recorded this season."

    monkeypatch.setitem(lp._PROVIDER_FUNCS, "groq", hallucinate)
    monkeypatch.setitem(lp._PROVIDER_FUNCS, "openrouter", grounded_answer)

    answer, provider = lp.generate_answer_multi("How many landslides?", ["12 landslides were recorded this season."])
    assert provider == "openrouter"
    assert "9999" not in answer


def test_multi_evaluation_comparison_reports_failures_for_unselected_providers(monkeypatch):
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")
    monkeypatch.setattr(lp.settings, "OPENROUTER_API_KEY", "k")

    def fail(*args, **kwargs):
        raise RuntimeError("simulated failure")

    def succeed(system_prompt, user_prompt):
        return "There were 12 landslides recorded this season."

    monkeypatch.setitem(lp._PROVIDER_FUNCS, "groq", fail)
    monkeypatch.setitem(lp._PROVIDER_FUNCS, "openrouter", succeed)

    _answer, provider, comparison = lp.generate_answer_multi_with_comparison(
        "How many landslides?", ["12 landslides were recorded this season."]
    )
    assert provider == "openrouter"
    statuses = {c["provider"]: c["status"] for c in comparison}
    assert statuses["groq"] == "request_failed"
    assert statuses["openrouter"] == "ok"
    # Gemini never appears in the comparison at all — it isn't part of the
    # chat chain, so it's never attempted or listed as skipped.
    assert "gemini" not in statuses


def test_multi_evaluation_raises_when_every_provider_fails(monkeypatch):
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")

    def fail(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(lp._PROVIDER_FUNCS, "groq", fail)

    with pytest.raises(lp.LLMUnavailable):
        lp.generate_answer_multi("question", ["context"])


def test_general_knowledge_fallback_unavailable_outside_multi_mode(monkeypatch):
    monkeypatch.setattr(lp.settings, "LLM_PROVIDER", "ollama")
    with pytest.raises(lp.LLMUnavailable):
        lp.generate_general_knowledge_answer("What should I do near a landslide?")


def test_general_knowledge_fallback_returns_provider_on_success(monkeypatch):
    monkeypatch.setattr(lp.settings, "GROQ_API_KEY", "k")

    def succeed(system_prompt, user_prompt):
        assert "general knowledge" in system_prompt.lower() or "GENERAL" in system_prompt
        return "In general, move away from steep slopes during heavy rain."

    monkeypatch.setitem(lp._PROVIDER_FUNCS, "groq", succeed)

    answer, provider = lp.generate_general_knowledge_answer("What should I do near a landslide?")
    assert provider == "groq"
    assert "steep slopes" in answer


def test_generate_answer_with_provider_single_mode_reports_configured_provider(monkeypatch):
    """Outside multi mode, generate_answer_with_provider must still report
    the single configured provider name (e.g. 'ollama'), not crash."""
    monkeypatch.setattr(lp.settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(lp.settings, "OLLAMA_BASE_URL", "http://localhost:11434")

    def fake_generate_answer(question, context_chunks):
        return "an answer"

    monkeypatch.setattr(lp, "generate_answer", fake_generate_answer)
    answer, provider = lp.generate_answer_with_provider("q", ["c"])
    assert answer == "an answer"
    assert provider == "ollama"


def test_generate_answer_with_provider_and_comparison_single_mode_has_no_comparison(monkeypatch):
    monkeypatch.setattr(lp.settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(lp.settings, "OLLAMA_BASE_URL", "http://localhost:11434")

    def fake_generate_answer(question, context_chunks):
        return "an answer"

    monkeypatch.setattr(lp, "generate_answer", fake_generate_answer)
    answer, provider, comparison = lp.generate_answer_with_provider_and_comparison("q", ["c"])
    assert answer == "an answer"
    assert provider == "ollama"
    assert comparison is None
