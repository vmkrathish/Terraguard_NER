"""
LLM provider abstraction.

Two modes, selected via LLM_PROVIDER:
  - A single provider ("openai" | "anthropic" | "ollama") — original
    behavior, unchanged: one provider, one call, fail or succeed.
  - "multi" — the chatbot's real runtime chain. Despite the name (kept for
    backward compatibility with existing deployments' .env files), this is
    NOT "call every provider and pick the best" anymore — it is a strict
    PRIMARY-THEN-FALLBACK chain:
      1. Groq is always tried first (see _chat_chain()).
      2. OpenRouter is only ever called if Groq raised an error OR its
         answer failed the groundedness check (see _is_grounded) — never
         when Groq already returned a good, grounded answer.
      3. Gemini is PERMANENTLY EXCLUDED from this chain, regardless of what
         LLM_PROVIDER_CHAIN is set to or whether GEMINI_API_KEY is present.
         Gemini support (_call_gemini, GEMINI_* settings) is kept in the
         codebase only for any non-chatbot use that may still reference it
         — it is never invoked from the chat/RAG answer path.
    Groundedness (see _is_grounded) is still a hard gate — an answer that
    invents a number not present in the real retrieved context is
    disqualified outright and treated the same as a failed request, which
    triggers the fallback to the next provider in the chain.
    The full per-provider outcome (attempted / skipped, status, latency,
    score) is returned alongside the winning answer as `comparison`, so a
    caller (the RAG API/UI) can show exactly what happened — including
    explicitly marking OpenRouter "not_called" when Groq already succeeded.

In every mode, the LLM is given the same instruction: answer ONLY from the
provided context, and say so explicitly if the context is inadequate — it
is never asked to supply a number, location, or statistic on its own that
TerraGuard's own database/knowledge base doesn't already contain. If no LLM
is configured, or every attempt fails, RAG falls back to a grounded
extract-based answer built directly from the retrieved chunks rather than
crashing or inventing official guidance.
"""
import re
import time
from typing import Optional

import httpx

from app.core.config import get_settings

settings = get_settings()


class LLMUnavailable(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


SYSTEM_PROMPT = (
    "You are a disaster-management guidance assistant for TerraGuard NER. "
    "Answer ONLY using the provided context excerpts from official SOP/guideline "
    "documents. If the context does not contain an adequate answer, say so explicitly "
    "instead of inventing official instructions. Be concise and actionable."
)


def is_llm_configured() -> bool:
    if settings.LLM_PROVIDER == "ollama":
        # Ollama is a local server with no API key — "configured" just means
        # it's selected. Whether it's actually reachable/running is checked
        # at call time in generate_answer(), same as the other providers.
        return bool(settings.OLLAMA_BASE_URL)
    if settings.LLM_PROVIDER == "multi":
        # Use the CHAT chain here, not the raw configured chain — if the
        # only key present is GEMINI_API_KEY, the chatbot still has no
        # usable provider (Gemini is never called from chat runtime), so
        # this must not report "configured" in that case.
        return bool(_chat_chain())
    return settings.LLM_PROVIDER in ("openai", "anthropic") and bool(settings.LLM_API_KEY)


# --- Chat provider chain (Groq primary, OpenRouter fallback only) ----------

def _configured_chain() -> list[str]:
    """The LLM_PROVIDER_CHAIN list, filtered down to providers that actually
    have an API key set — an unconfigured provider is silently skipped
    rather than attempted and failing every time. This is a general-purpose
    helper (e.g. used to report "which providers have keys set" on
    /health) — it is NOT what decides what the chatbot actually calls; see
    _chat_chain() for that."""
    keys = {
        "gemini": settings.GEMINI_API_KEY,
        "groq": settings.GROQ_API_KEY,
        "openrouter": settings.OPENROUTER_API_KEY,
    }
    order = [p.strip().lower() for p in settings.LLM_PROVIDER_CHAIN.split(",") if p.strip()]
    return [p for p in order if keys.get(p)]


def configured_chain_providers() -> list[str]:
    """Public wrapper around _configured_chain(), for callers outside this
    module (e.g. the /health endpoint) that want to show which providers
    have an API key set right now — informational only, not necessarily
    what the chatbot itself will call (see configured_chat_chain())."""
    return _configured_chain()


# The ONLY two providers the chatbot/RAG runtime is ever allowed to call,
# in the fixed order required: Groq first, OpenRouter only as a fallback.
# Gemini is intentionally absent from this tuple — no matter what
# LLM_PROVIDER_CHAIN says, or whether GEMINI_API_KEY is set, Gemini is never
# part of the chat chain.
_CHAT_PROVIDER_ORDER = ("groq", "openrouter")


def _chat_chain() -> list[str]:
    """The actual chain the chatbot uses: Groq, then OpenRouter — each
    included only if its API key is set — with Gemini always excluded,
    regardless of LLM_PROVIDER_CHAIN's contents or order. This is what
    generate_answer_multi_with_comparison() and
    generate_general_knowledge_answer_with_comparison() call every request;
    _configured_chain() (used for informational display) is not."""
    configured = set(_configured_chain())
    return [p for p in _CHAT_PROVIDER_ORDER if p in configured]


def configured_chat_chain() -> list[str]:
    """Public wrapper around _chat_chain(), for callers outside this module
    (e.g. the /health endpoint) that want to show exactly what the chatbot
    will call, in order — never includes Gemini."""
    return _chat_chain()


def _call_openai_compatible(base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    """Shared implementation for the two providers (Groq, OpenRouter) that
    expose an OpenAI-compatible chat-completions endpoint — only the base
    URL, key, and model differ between them."""
    resp = httpx.post(
        base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 600,
        },
        timeout=settings.LLM_PROVIDER_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    message = data["choices"][0]["message"]
    text = message.get("content") or ""
    # Some reasoning models (e.g. DeepSeek-R1 via OpenRouter) can return the
    # visible answer in a separate "reasoning" field when content is empty
    # for a particular response shape — fall back to it rather than
    # returning a blank answer.
    if not text.strip() and message.get("reasoning"):
        text = message["reasoning"]
    return text.strip()


def _call_groq(system_prompt: str, user_prompt: str) -> str:
    return _call_openai_compatible(
        "https://api.groq.com/openai/v1/chat/completions",
        settings.GROQ_API_KEY, settings.GROQ_MODEL, system_prompt, user_prompt,
    )


def _call_openrouter(system_prompt: str, user_prompt: str) -> str:
    return _call_openai_compatible(
        "https://openrouter.ai/api/v1/chat/completions",
        settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL, system_prompt, user_prompt,
    )


def _call_gemini(system_prompt: str, user_prompt: str) -> str:
    resp = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent",
        params={"key": settings.GEMINI_API_KEY},
        json={
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600},
        },
        timeout=settings.LLM_PROVIDER_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        # Most commonly a safety-filter block — treat as a normal failure so
        # evaluation moves on with whatever other providers returned instead
        # of crashing.
        raise LLMUnavailable(f"Gemini returned no candidates: {data.get('promptFeedback')}")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


_PROVIDER_FUNCS = {
    "gemini": _call_gemini,
    "groq": _call_groq,
    "openrouter": _call_openrouter,
}


_NUMBER_RE = re.compile(r"\d[\d,]*\.?\d*")


def _is_grounded(answer: str, context_chunks: list[str]) -> tuple[bool, Optional[str]]:
    """A lightweight, automated faithfulness check run on every multi-provider
    answer BEFORE it is eligible to be selected — this is the "evaluate
    properly before serving" step: an LLM's fluent-sounding answer is not
    trusted just because it returned 200 OK. It never blocks a normal
    explanatory answer; it specifically catches the case that matters most
    for this project's no-fabrication rule — a NEW number appearing in the
    answer that isn't anywhere in the real context it was supposed to be
    grounded in (a classic hallucination pattern: a plausible-looking
    statistic the model invented rather than read).

    This is a heuristic, not a proof of correctness — it cannot catch every
    kind of hallucination (a wrong claim using a real number from the
    context would pass) — but it is a real, automated check that runs on
    every answer, not a rubber stamp, and it directly enforces the
    project's standing "never invent a number" rule at the point where a
    free-tier LLM (which this project does not otherwise control or trust)
    is the one generating text.
    """
    if not answer or len(answer.strip()) < 3:
        return False, "empty_or_too_short"

    context_text = "\n".join(context_chunks)
    context_numbers = {m.replace(",", "") for m in _NUMBER_RE.findall(context_text)}

    for raw in _NUMBER_RE.findall(answer):
        normalized = raw.replace(",", "")
        # Single digits (0-9) are excluded — far too common in ordinary
        # prose ("3 steps", "step 1") to be a meaningful groundedness signal,
        # and flagging them produces mostly false positives.
        if len(normalized.replace(".", "")) < 2:
            continue
        if normalized not in context_numbers:
            return False, f"ungrounded_number:{raw}"

    return True, None


def _score_candidate(answer: str, latency_seconds: float) -> float:
    """Heuristic quality score (0-100, NOT a real correctness measure),
    reported alongside a winning answer in `comparison` purely for
    visibility into how good/fast that specific answer was — it no longer
    ranks multiple providers against each other (the chain stops at the
    first grounded success; see _evaluate_all_providers), but is still
    useful as a quick quality readout in the UI. Only ever computed for an
    answer that has already passed the groundedness gate (see
    _is_grounded) — an ungrounded answer is disqualified before this
    function runs, never scored and never treated as a success.

    Composed of:
      - completeness (75% weight): a longer, non-trivial answer scores
        higher, capped at 500 characters — a real, full response isn't
        rewarded further just for being padded beyond that.
      - responsiveness (25% weight): a faster provider scores a little
        higher, as a tie-breaker only — this can never be enough on its
        own to let a fast, thin answer beat a thorough one, since it's a
        quarter of the total weight versus completeness's three quarters.
    """
    length = len(answer.strip())
    completeness = min(length, 500) / 500.0
    if length < 20:
        completeness *= 0.4
    responsiveness = max(0.0, 1.0 - (latency_seconds / max(settings.LLM_PROVIDER_TIMEOUT_SECONDS, 1.0)))
    score = (completeness * 0.75) + (responsiveness * 0.25)
    return round(score * 100, 1)


def _evaluate_all_providers(
    chain: list[str],
    system_prompt: str,
    user_prompt: str,
    context_chunks: Optional[list[str]],
) -> tuple[Optional[tuple[str, str]], list[dict]]:
    """Calls providers in `chain` IN ORDER, one at a time, stopping at the
    first one that returns a good, grounded answer — this is the required
    primary-then-fallback behavior: `chain` is always Groq-then-OpenRouter
    (see _chat_chain()), so in practice this means "try Groq; only call
    OpenRouter if Groq failed or was rejected." A later provider in `chain`
    is NEVER called once an earlier one has already succeeded — it is
    recorded in `comparison` with status "not_called" instead, so the UI can
    show plainly that it was skipped, not that it was tried and failed.

    `context_chunks=None` skips the groundedness check entirely (used only
    for the general-knowledge fallback, which by design has no real
    TerraGuard context to check an answer against — see
    generate_general_knowledge_answer_with_comparison); passing a list
    (even an empty one) enables the check.

    Returns (winner_or_None, comparison). `comparison` is a list of
    per-provider result dicts safe to expose to the API/UI — provider name,
    status, timing, and score only; never a raw exception, stack trace, or
    API key."""
    comparison: list[dict] = []
    winner: Optional[tuple[str, str]] = None

    for provider in chain:
        if winner is not None:
            # An earlier provider in the chain already produced a good
            # answer — every later provider is deliberately skipped, not
            # called "just in case", so a working Groq answer never waits
            # on (or triggers) an OpenRouter request.
            comparison.append({"provider": provider, "status": "not_called"})
            continue

        func = _PROVIDER_FUNCS[provider]
        start = time.monotonic()
        try:
            answer = func(system_prompt, user_prompt)
        except Exception as exc:  # noqa: BLE001 — one provider's failure must not crash evaluation
            comparison.append({
                "provider": provider,
                "status": "request_failed",
                "error": str(exc)[:200],
                "latency_ms": round((time.monotonic() - start) * 1000),
            })
            continue

        latency = time.monotonic() - start
        if context_chunks is not None:
            grounded, reason = _is_grounded(answer, context_chunks)
            if not grounded:
                comparison.append({
                    "provider": provider,
                    "status": "failed_groundedness_check",
                    "reason": reason,
                    "latency_ms": round(latency * 1000),
                })
                continue
        else:
            grounded = None

        comparison.append({
            "provider": provider,
            "status": "ok",
            "grounded": grounded,
            "score": _score_candidate(answer, latency),
            "latency_ms": round(latency * 1000),
            "selected_as_optimal": True,
        })
        winner = (answer, provider)

    return winner, comparison


def generate_answer_multi_with_comparison(question: str, context_chunks: list[str]) -> tuple[str, str, list[dict]]:
    """Tries Groq first; only calls OpenRouter if Groq errored or failed
    groundedness. Gemini is never called here. Returns
    (answer, provider_used, comparison) — `comparison` shows each attempted
    provider's outcome, plus "not_called" for OpenRouter when Groq already
    succeeded, suitable for showing exactly what happened in the API/UI.
    Raises LLMUnavailable only if no provider is configured, or every
    configured provider in the chain failed the request itself or failed
    the groundedness check."""
    chain = _chat_chain()
    if not chain:
        raise LLMUnavailable(
            "LLM_PROVIDER='multi' but neither GROQ_API_KEY nor OPENROUTER_API_KEY is set. "
            "(Gemini is never used for chat, even if GEMINI_API_KEY is set.)"
        )

    context = "\n\n---\n\n".join(context_chunks)
    user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

    winner, comparison = _evaluate_all_providers(chain, SYSTEM_PROMPT, user_prompt, context_chunks)
    if winner is None:
        failures = "; ".join(
            f"{c['provider']}: {c['status']}" + (f" ({c.get('reason') or c.get('error')})" if c.get("reason") or c.get("error") else "")
            for c in comparison
        )
        raise LLMUnavailable(f"All configured providers failed evaluation: {failures}")

    answer, provider = winner
    return answer, provider, comparison


def generate_answer_multi(question: str, context_chunks: list[str]) -> tuple[str, str]:
    """Back-compat wrapper around generate_answer_multi_with_comparison() for
    callers that only need the winning answer, not the full comparison."""
    answer, provider, _comparison = generate_answer_multi_with_comparison(question, context_chunks)
    return answer, provider


GENERAL_KNOWLEDGE_SYSTEM_PROMPT = (
    "You are a disaster-management assistant. TerraGuard's own data records and knowledge base have "
    "NO record covering this specific question. Answer using your own general knowledge of "
    "landslide safety, evacuation, and disaster-management best practice ONLY. You MUST NOT claim, "
    "imply, or phrase your answer as if this came from TerraGuard's own records, sensors, "
    "historical data, or predictions — it did not. Do not state specific place names, dates, risk "
    "scores, casualty figures, or other precise statistics as if they were verified facts about a "
    "real location or event, since none of that can be checked here — speak in general terms "
    "(typical precautions, general best practice) instead. Be concise and actionable."
)


def generate_general_knowledge_answer_with_comparison(question: str) -> tuple[str, str, list[dict]]:
    """Only used when TerraGuard's own structured DB and document knowledge
    base both have nothing on a question (see rag_pipeline._general_knowledge_answer)
    and LLM_PROVIDER='multi' — i.e. this is opt-in, not the default RAG
    behavior. Tries Groq first, falls back to OpenRouter only if Groq fails
    — same primary/fallback chain as generate_answer_multi_with_comparison,
    and Gemini is likewise never called — but with a DIFFERENT system prompt
    that explicitly forbids the model from presenting its own general
    knowledge as if it were verified TerraGuard data, and deliberately does
    NOT run _is_grounded() — there is no retrieved context to ground against
    here by definition, so the first provider to respond with a non-empty
    answer wins. The honesty guarantee for this path comes from the system
    prompt and the answer_type="general_knowledge" label the frontend must
    display, not from a groundedness check."""
    if settings.LLM_PROVIDER != "multi":
        raise LLMUnavailable("General-knowledge fallback is only available when LLM_PROVIDER='multi'.")
    chain = _chat_chain()
    if not chain:
        raise LLMUnavailable("No provider in the chat chain (Groq, OpenRouter) has an API key set.")

    winner, comparison = _evaluate_all_providers(chain, GENERAL_KNOWLEDGE_SYSTEM_PROMPT, question, None)
    if winner is None:
        failures = "; ".join(f"{c['provider']}: {c['status']}" for c in comparison)
        raise LLMUnavailable(f"All configured providers failed for the general-knowledge fallback: {failures}")

    answer, provider = winner
    return answer, provider, comparison


def generate_general_knowledge_answer(question: str) -> tuple[str, str]:
    """Back-compat wrapper around generate_general_knowledge_answer_with_comparison()."""
    answer, provider, _comparison = generate_general_knowledge_answer_with_comparison(question)
    return answer, provider


def generate_answer(question: str, context_chunks: list[str]) -> str:
    """Single-provider path (openai / anthropic / ollama) — unchanged
    behavior from before the multi-provider evaluation existed. For
    LLM_PROVIDER='multi', use generate_answer_with_provider_and_comparison()
    instead (this function still works for 'multi' too, it just discards
    which provider answered and the comparison)."""
    if settings.LLM_PROVIDER == "multi":
        answer, _provider = generate_answer_multi(question, context_chunks)
        return answer

    if not is_llm_configured():
        raise LLMUnavailable(
            f"No LLM configured (LLM_PROVIDER='{settings.LLM_PROVIDER}', key present={bool(settings.LLM_API_KEY)})."
        )

    context = "\n\n---\n\n".join(context_chunks)
    system_prompt = SYSTEM_PROMPT
    user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

    try:
        if settings.LLM_PROVIDER == "openai":
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                json={
                    "model": settings.LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        if settings.LLM_PROVIDER == "anthropic":
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.LLM_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": settings.LLM_MODEL,
                    "max_tokens": 600,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]

        if settings.LLM_PROVIDER == "ollama":
            # Ollama's OpenAI-compatible-ish chat endpoint, running fully
            # locally — no API key, no internet call. Requires the Ollama
            # app to be running and the model in LLM_MODEL to be pulled
            # already (`ollama pull <model>`).
            #
            # The 30-80s latency the user reported traces to qwen3 models'
            # "thinking" mode: by default they emit a long internal
            # <think>...</think> reasoning block before the real answer, and
            # that hidden block is often several times longer than the answer
            # itself. Turning it off (supported by Ollama for qwen3 via the
            # top-level "think" field), capping output length (num_predict)
            # and bounding the context window (num_ctx, sized for our actual
            # ~4-chunk / ~3.6k-char prompts) removes that wasted generation
            # time without changing what real context the model sees.
            resp = httpx.post(
                f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                json={
                    "model": settings.LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "think": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 350,
                        "num_ctx": 2048,
                    },
                },
                # Local inference on a laptop CPU/GPU can be much slower than
                # a cloud API — give it a generous timeout instead of failing
                # a slow-but-working setup. (With thinking disabled and output
                # capped, actual generation should land well under this.)
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()["message"]["content"]
            # Defensive: on an older Ollama build (or a qwen3 build that only
            # partially honors "think": false), the response can contain a
            # full <think>...</think> block, OR — as observed — just a stray
            # "</think>" with no matching opening tag (the opening tag was
            # suppressed but the model still emitted its closing marker).
            # Handle both cases so no thinking-mode artifact ever reaches
            # the user.
            if "<think>" in data:
                data = data.split("</think>", 1)[-1] if "</think>" in data else data.split("<think>", 1)[0]
            elif "</think>" in data:
                data = data.replace("</think>", "")
            return data.strip()

        raise LLMUnavailable(f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'.")
    except LLMUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LLMUnavailable(f"LLM provider call failed: {exc}") from exc


def generate_answer_with_provider(question: str, context_chunks: list[str]) -> tuple[str, str]:
    """Like generate_answer(), but also returns which provider actually
    produced the answer — "groq" / "gemini" / "openrouter" for the
    multi-provider evaluation, or the single configured LLM_PROVIDER name
    otherwise."""
    if settings.LLM_PROVIDER == "multi":
        return generate_answer_multi(question, context_chunks)
    return generate_answer(question, context_chunks), settings.LLM_PROVIDER


def generate_answer_with_provider_and_comparison(
    question: str, context_chunks: list[str]
) -> tuple[str, str, Optional[list[dict]]]:
    """Like generate_answer_with_provider(), but also returns the full
    per-provider comparison when LLM_PROVIDER='multi' (None in single-
    provider mode, since there is nothing to compare). This is what the RAG
    API/UI should call to show "which of the 3 configured LLMs was optimal
    for this answer" alongside the answer itself."""
    if settings.LLM_PROVIDER == "multi":
        return generate_answer_multi_with_comparison(question, context_chunks)
    return generate_answer(question, context_chunks), settings.LLM_PROVIDER, None
