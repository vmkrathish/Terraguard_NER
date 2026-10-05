"""
Regression test for a `</think>` tag leaking into the visible answer (seen
live: "89 landslides occurred in Assam" prefixed with a stray "</think>").

qwen3 models' "thinking" mode is requested off ("think": False) but some
Ollama builds only partially honor it — the ORIGINAL bug only stripped
content when BOTH "<think>" and "</think>" were present, so a response
containing just a stray "</think>" (no opening tag) passed through
untouched. This test locks in the fix: every combination is handled.
"""
import httpx
import pytest

from app.services import llm_providers as lp


class _FakeResponse:
    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": self._content}}


@pytest.fixture(autouse=True)
def _ollama_settings(monkeypatch):
    monkeypatch.setattr(lp.settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(lp.settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(lp.settings, "LLM_MODEL", "qwen3:4b")


def _run(monkeypatch, raw_content: str) -> str:
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(raw_content))
    return lp.generate_answer("how many landslides in Assam", ["some context chunk"])


def test_strips_stray_closing_tag_with_no_opening_tag(monkeypatch):
    """The exact bug observed: a lone "</think>" with no matching opener."""
    raw = "</think>\n\nAccording to TerraGuard's historical dataset, 89 landslides occurred in Assam."
    result = _run(monkeypatch, raw)
    assert "</think>" not in result
    assert "<think>" not in result
    assert result.startswith("According to TerraGuard")


def test_strips_full_think_block(monkeypatch):
    raw = "<think>reasoning about the question...</think>The answer is 89 landslides."
    result = _run(monkeypatch, raw)
    assert "<think>" not in result and "</think>" not in result
    assert result == "The answer is 89 landslides."


def test_strips_unclosed_opening_tag(monkeypatch):
    raw = "<think>still reasoning with no closing tag at all"
    result = _run(monkeypatch, raw)
    assert result == ""


def test_leaves_normal_answer_untouched(monkeypatch):
    raw = "89 landslides occurred in Assam according to TerraGuard's records."
    result = _run(monkeypatch, raw)
    assert result == raw
