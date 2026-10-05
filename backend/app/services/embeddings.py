"""
Embedding provider for the RAG pipeline.

BAAI/bge-m3, a real multilingual semantic embedding model, run locally via
sentence-transformers (CPU is fine — no GPU required, no API key, no
per-call cost).

First use downloads the model weights (~2.3 GB) from Hugging Face — no
login/token required, it's a fully public model. After that first
download, everything runs offline.

Graceful degradation: if `sentence-transformers`/`torch` aren't installed,
or the model can't be downloaded (no internet on first run), embed_text()
falls back to a local HashingVectorizer — resized to the same
EMBEDDING_DIM so the database column never has to change based on which
backend happens to be active. This keeps the app running end-to-end, but
retrieval quality drops to keyword-overlap in that mode. Check
embedding_status() (surfaced on /health) to see which backend is actually
active — a project that cares about answer quality should not ship with
the fallback active long-term.
"""
import logging
import threading
from typing import Optional

import numpy as np

from app.core.config import get_settings
from app.core.native_init_lock import NATIVE_INIT_LOCK

settings = get_settings()
logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()
_load_failed_reason: Optional[str] = None

_fallback_vectorizer = None


def _get_bge_model(block: bool = True):
    """Lazily load the BGE-M3 model on first use (not at import time, so a
    missing/failed model doesn't crash app startup or `--reload`).

    `block=True` (the default) waits for a load already in progress to
    finish — fine for the one background thread main.py's startup event
    kicks off, since nothing is waiting on it.

    `block=False` is what the live request path (embed_texts, below) uses:
    if the model is already loaded, return it immediately; if a load is
    already in progress (the background preload thread, or a race with
    another request) it returns None right away instead of waiting —
    the caller falls back to the hashing vectorizer for THIS call only.
    Without this, a user's question could sit blocked for however long a
    slow/failing ~2.3GB download takes, which is exactly the "no reply
    shows up" problem this preload was meant to fix, not cause."""
    global _model, _load_failed_reason
    if _model is not None or _load_failed_reason is not None:
        return _model
    acquired = _model_lock.acquire(blocking=block)
    if not acquired:
        return None
    try:
        if _model is not None or _load_failed_reason is not None:
            return _model
        try:
            # See app/core/native_init_lock.py: hold the lock only around the
            # `import torch` line below — that's the single moment PyTorch's
            # bundled OpenMP runtime actually initializes. The lock must NOT
            # wrap the SentenceTransformer(...) call below it: that call can
            # take anywhere from seconds (warm HF cache) to minutes (a cold
            # ~2.3GB download), and holding a shared lock for that whole
            # span would make every /risk/predict call block for just as
            # long the first time both happen close together — trading a
            # rare segfault for a much more common multi-minute API hang.
            with NATIVE_INIT_LOCK:
                import torch  # noqa: F401

            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s (first run downloads ~2.3GB, then cached)...", settings.EMBEDDING_MODEL)
            _model = SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu")
            logger.info("Embedding model loaded.")
        except Exception as exc:  # noqa: BLE001 — must never crash the app; fall back instead
            _load_failed_reason = str(exc)
            logger.warning(
                "Could not load embedding model '%s' (%s). Falling back to a low-quality local "
                "hashing embedding. Install `sentence-transformers`/`torch` and ensure internet "
                "access for the first run to fix this.",
                settings.EMBEDDING_MODEL,
                exc,
            )
    finally:
        _model_lock.release()
    return _model


def _get_fallback_vectorizer():
    global _fallback_vectorizer
    if _fallback_vectorizer is None:
        from sklearn.feature_extraction.text import HashingVectorizer

        _fallback_vectorizer = HashingVectorizer(n_features=settings.EMBEDDING_DIM, alternate_sign=False, norm="l2")
    return _fallback_vectorizer


def embedding_status() -> dict:
    """Which embedding backend is actually active right now, for /health."""
    if _model is not None:
        return {"backend": "bge-m3", "model": settings.EMBEDDING_MODEL, "dim": settings.EMBEDDING_DIM, "semantic": True}
    if _load_failed_reason is not None:
        return {
            "backend": "hashing_fallback",
            "model": None,
            "dim": settings.EMBEDDING_DIM,
            "semantic": False,
            "reason": _load_failed_reason,
        }
    return {"backend": "not_loaded_yet", "model": settings.EMBEDDING_MODEL, "dim": settings.EMBEDDING_DIM, "semantic": None}


def embed_text(text: str, for_query: bool = True) -> list[float]:
    return embed_texts([text], for_query=for_query)[0]


def embed_texts(texts: list[str], for_query: bool = False) -> list[list[float]]:
    """Batch-embed multiple texts in one call — much faster than calling
    embed_text() in a loop during ingestion of many chunks.

    `for_query` distinguishes a live user question (True) from a document
    chunk being indexed (False, the default — ingestion always embeds
    chunks in batches). BGE-M3 and the hashing fallback both ignore this
    distinction — it's accepted for API-compatibility with callers, but
    only matters for an asymmetric hosted embedding provider, which this
    project does not use."""
    # non-blocking: never make a live request wait on a model load that's
    # already in progress (background preload, or another concurrent
    # request) — use the fallback for this call instead, and future calls
    # pick up the real model automatically once it finishes loading.
    model = _get_bge_model(block=False)
    if model is not None:
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.astype(float).tolist() for v in vectors]

    # Fallback path: hashing vectorizer, resized to the same dimension so the
    # database column type never has to differ based on which backend loaded.
    vectorizer = _get_fallback_vectorizer()
    matrix = vectorizer.transform(texts).toarray()
    out = []
    for vec in matrix:
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        out.append(vec.astype(float).tolist())
    return out
