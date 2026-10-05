"""
RAG pipeline: chunking, embedding, in-process cosine-similarity search
(numpy, over vectors stored in the Excel `rag_chunks` sheet), and grounded
answer generation with graceful LLM fallback.

RAG is a SUPPORTING layer here (SOPs, evacuation guidance, response
recommendations) — it never determines risk probability/score/level, which
comes only from the ML risk engine (see app.services.risk_engine) or from
real rows in the Excel-backed store (see app.services.query_router).

Hybrid routing lives here too: answer_query() first asks query_router to
classify the question as "structured" (a real data lookup — numbers),
"document" (RAG over knowledge_base/), or "combined" (both). Structured
facts are ALWAYS computed by SQL, never invented by the LLM — the LLM's only
job on a structured/combined question is to explain already-computed facts
in plain language, never to add new numbers.
"""
import datetime as dt
import hashlib
import json
import logging
import os
import random
from typing import Optional

import numpy as np

from app.core.config import get_settings
from app.core.excel_store import Store
from app.services.embeddings import embed_text, embed_texts, embedding_status
from app.services.llm_providers import (
    LLMUnavailable, generate_answer_with_provider_and_comparison,
    generate_general_knowledge_answer_with_comparison, is_llm_configured,
)
from app.services import query_router

_settings = get_settings()
logger = logging.getLogger(__name__)

CHUNK_SIZE_CHARS = 900
CHUNK_OVERLAP_CHARS = 150


def chunk_text(content: str) -> list[str]:
    content = content.strip()
    if not content:
        return []
    chunks = []
    start = 0
    while start < len(content):
        end = min(start + CHUNK_SIZE_CHARS, len(content))
        chunks.append(content[start:end])
        if end == len(content):
            break
        start = end - CHUNK_OVERLAP_CHARS
    return chunks


def _extract_pdf_pages(path: str) -> list[str]:
    """Returns a list of per-page text strings. Requires `pypdf` (added to
    requirements.txt); if it's missing, raises so the caller can skip the
    file with a clear message rather than silently ingesting nothing."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    return [(page.extract_text() or "") for page in reader.pages]


def _read_file_for_ingestion(path: str, fname: str) -> tuple[str, list[dict]]:
    """Returns (full_text_for_hashing, chunk_records) where chunk_records is
    a list of {"text": ..., "metadata": {...}} — one entry per chunk, already
    split, with page/section metadata attached for PDFs."""
    if fname.lower().endswith(".pdf"):
        pages = _extract_pdf_pages(path)
        full_text = "\n".join(pages)
        chunk_records = []
        for page_num, page_text in enumerate(pages, start=1):
            for piece in chunk_text(page_text):
                chunk_records.append({"text": piece, "metadata": {"filename": fname, "page": page_num}})
        return full_text, chunk_records

    # .txt / .md
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    chunk_records = [{"text": piece, "metadata": {"filename": fname}} for piece in chunk_text(content)]
    return content, chunk_records


SUPPORTED_EXTENSIONS = (".txt", ".md", ".pdf")


def ingest_directory(store: Store, directory: str) -> dict:
    documents_ingested = 0
    chunks_created = 0
    skipped = []

    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith(SUPPORTED_EXTENSIONS):
            skipped.append(f"{fname} (unsupported file type — supported: .txt, .md, .pdf)")
            continue
        path = os.path.join(directory, fname)

        try:
            full_text, chunk_records = _read_file_for_ingestion(path, fname)
        except Exception as exc:  # noqa: BLE001 — one bad file must not abort the whole ingest run
            skipped.append(f"{fname} (could not read file: {exc})")
            continue

        content_hash = hashlib.sha256(full_text.encode("utf-8", errors="ignore")).hexdigest()

        docs = store.df("rag_documents")
        if not docs[docs["content_hash"] == content_hash].empty:
            skipped.append(f"{fname} (already ingested, unchanged)")
            continue

        if not chunk_records:
            skipped.append(f"{fname} (no extractable text)")
            continue

        now = dt.datetime.now(dt.timezone.utc).isoformat()
        doc = store.insert("rag_documents", {
            "title": fname, "source": "knowledge_base", "filepath": path,
            "content_hash": content_hash, "ingested_at": now,
        }, persist=False)
        doc_id = doc["id"]

        # Batch-embed all chunks of this document in one model call — much
        # faster than one embed_text() call per chunk.
        embeddings = embed_texts([rec["text"] for rec in chunk_records])
        for i, (rec, embedding) in enumerate(zip(chunk_records, embeddings)):
            meta = dict(rec["metadata"])
            meta["chunk_id"] = f"{fname}#{i}"
            store.insert("rag_chunks", {
                "document_id": doc_id, "chunk_index": i, "content": rec["text"],
                "embedding": list(embedding), "metadata": meta, "created_at": now,
            }, persist=False)
        chunks_created += len(chunk_records)
        documents_ingested += 1

    store.save()
    return {"documents_ingested": documents_ingested, "chunks_created": chunks_created, "skipped": skipped}


def reembed_all_chunks(store: Store, batch_size: int = 16) -> dict:
    """Recomputes embeddings for every existing chunk using the currently
    configured embedding backend, WITHOUT touching chunk text/metadata or
    re-reading source files. Needed after switching embedding models/dims,
    or any time you want existing chunks re-embedded with a newer model."""
    df = store.df("rag_chunks").sort_values("id")
    updated = 0
    for start in range(0, len(df), batch_size):
        batch = df.iloc[start : start + batch_size]
        embeddings = embed_texts(batch["content"].tolist())
        for (_, row), embedding in zip(batch.iterrows(), embeddings):
            store.update_where("rag_chunks", "id", int(row["id"]), {"embedding": list(embedding)}, persist=False)
        updated += len(batch)
    if updated:
        store.save()
    return {"chunks_reembedded": updated, "backend": embedding_status()}


def similarity_search(store: Store, query: str, top_k: int = 4) -> list[dict]:
    """Cosine-similarity top-k retrieval done in-process over the
    Excel-backed `rag_chunks` sheet's stored embeddings (JSON-encoded lists
    of floats), replacing pgvector's `<=>` operator + ivfflat/exact index."""
    chunks = store.df("rag_chunks")
    chunks = chunks[chunks["embedding"].apply(lambda v: isinstance(v, list) and len(v) > 0)]
    if chunks.empty:
        return []
    docs = store.df("rag_documents").set_index("id")

    query_vec = np.array(embed_text(query), dtype=float)
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []

    matrix = np.array(chunks["embedding"].tolist(), dtype=float)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1e-12
    similarities = (matrix @ query_vec) / (norms * query_norm)

    chunks = chunks.assign(similarity=similarities)
    top = chunks.sort_values("similarity", ascending=False).head(top_k)

    results = []
    for _, r in top.iterrows():
        doc_id = r["document_id"]
        doc = docs.loc[doc_id] if doc_id in docs.index else None
        results.append({
            "content": r["content"],
            "chunk_index": int(r["chunk_index"]),
            "metadata": r["metadata"],
            "title": doc["title"] if doc is not None else "unknown",
            "source": doc["source"] if doc is not None else None,
            "similarity": float(r["similarity"]),
        })
    return results


# Similarity thresholds differ meaningfully by embedding backend:
#  - BGE-M3 produces normalized semantic embeddings whose cosine similarity
#    for genuinely related passages typically sits well above 0.3-0.4; using
#    the old hashing-vectorizer threshold here would accept weak matches.
#  - The hashing-vectorizer fallback produces much lower-magnitude cosine
#    similarities even for good keyword overlaps, so it needs a lower bar —
#    but 0.05 (5%) turned out to be too low in practice: a near-random
#    keyword overlap can clear it, gets treated as "adequate," and gets
#    handed to the LLM, which then produces an answer that reads confident
#    but isn't actually grounded in anything relevant — exactly the
#    "explained by LLM" reply sitting on top of barely-related 5%-match
#    excerpts this was raised about. Raised to 0.12 so only a real,
#    non-trivial keyword overlap counts as adequate for this backend.
SEMANTIC_MIN_ADEQUATE_SIMILARITY = 0.30
FALLBACK_MIN_ADEQUATE_SIMILARITY = 0.12


def _min_adequate_similarity() -> float:
    status = embedding_status()
    if status.get("backend") == "bge-m3":
        return SEMANTIC_MIN_ADEQUATE_SIMILARITY
    return FALLBACK_MIN_ADEQUATE_SIMILARITY


def _clean_excerpt(raw: str, max_chars: int = 220) -> str:
    """Strips raw Markdown syntax (#, *, >, -) from a chunk before it's
    shown as a source excerpt in the UI, and cuts at a word boundary
    instead of mid-word. Source chunks are stored verbatim (correct for
    retrieval/embedding), but showing that raw Markdown straight in a chat
    bubble reads as garbled noise rather than the sentence it actually is."""
    text = raw.strip()
    lines = []
    for line in text.splitlines():
        line = line.strip()
        line = line.lstrip("#").strip()  # heading markers
        line = line.lstrip(">").strip()  # blockquote markers
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        line = line.replace("**", "").replace("`", "")
        if line:
            lines.append(line)
    cleaned = " ".join(lines)
    if len(cleaned) <= max_chars:
        return cleaned
    truncated = cleaned[:max_chars].rsplit(" ", 1)[0]
    return truncated + "…"


def _sources_from_results(results: list[dict]) -> list[dict]:
    sources = []
    for r in results:
        meta = r.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except ValueError:
                meta = {}
        sources.append(
            {
                "title": r["title"],
                "source": r["source"],
                "chunk_index": r["chunk_index"],
                "similarity": round(r["similarity"], 3),
                "excerpt": _clean_excerpt(r["content"]),
                "page": meta.get("page"),
            }
        )
    return sources


# Phrases that indicate the LLM itself concluded the retrieved context does
# NOT actually answer the question, even though similarity search judged the
# chunks "adequate" (a semantic-similarity score only measures topical
# closeness — e.g. "evacuation guidance" and "when did a landslide last
# happen" score as related, without either one containing the other's
# answer). When the LLM says so, trust that over the similarity score: show
# the clean "insufficient data" state instead of a green "found it" badge
# sitting on top of a wall of excerpts the model itself just said don't help.
_NO_ANSWER_PHRASES = (
    "does not provide", "do not provide", "doesn't provide",
    "does not contain", "do not contain", "doesn't contain",
    "not contain enough information", "cannot determine", "can't determine",
    "no information", "not available in", "not mentioned in",
    "insufficient information", "unable to determine", "unable to answer",
    "context does not", "documents do not", "cannot find", "can't find",
)


def _llm_declined_to_answer(answer_text: str) -> bool:
    lowered = answer_text.lower()
    return any(phrase in lowered for phrase in _NO_ANSWER_PHRASES)


def _general_knowledge_answer(question: str) -> Optional[dict]:
    """Last-resort fallback, opt-in only (LLM_PROVIDER='multi'): when
    TerraGuard's own database and knowledge base genuinely have nothing on a
    question, ask the configured multi-provider LLM chain for GENERAL
    disaster-management knowledge instead of returning nothing. This is
    deliberately a different, more restrictive path than the normal
    document/structured answers — it is labeled answer_type="general_knowledge"
    (not "document" or "structured") specifically so the UI can show it with
    a visible "general knowledge, not a verified TerraGuard record" notice,
    and it is never used to answer questions about specific TerraGuard-
    tracked risk scores, predictions, or historical records — those always
    come from the ML engine or real database rows (see risk_engine.py /
    query_router.py), never from this fallback.

    Returns None (not a dict) when the fallback itself isn't available
    (LLM_PROVIDER isn't 'multi', or every provider failed) — the caller then
    falls through to the normal honest "insufficient_data" response."""
    if _settings.LLM_PROVIDER != "multi":
        return None
    try:
        answer, provider_used, comparison = generate_general_knowledge_answer_with_comparison(question)
    except LLMUnavailable:
        return None
    return {
        "answer": (
            "TerraGuard has no specific record covering this question. Here is general "
            "disaster-management guidance instead — this is NOT a verified TerraGuard record, "
            "prediction, or historical fact, just general knowledge:\n\n" + answer
        ),
        "sources": [],
        "llm_used": True,
        "provider": provider_used,
        "fallback_reason": "no_terraguard_record_used_general_knowledge",
        "answer_type": "general_knowledge",
        "structured_rows": [],
        "query_description": None,
        "llm_comparison": comparison,
    }


import random

_GREETING_REPLIES = [
    "Hey! I'm the TerraGuard NER assistant — ask me about landslide risk, historical events, "
    "rainfall, or evacuation guidance for the North-East India region, and I'll pull real data "
    "or SOP guidance for you.",
    "Hello! I can help with landslide risk levels, historical incident data, rainfall, and "
    "evacuation/response guidance for the NE India states TerraGuard covers. What would you "
    "like to know?",
    "Hi there! Ask me things like \"how many landslides in Assam\" or \"evacuation steps for "
    "high-risk zones\" and I'll answer from TerraGuard's real records and SOP documents.",
]

_THANKS_REPLIES = [
    "You're welcome! Let me know if you need anything else on landslide risk or response guidance.",
    "Happy to help — feel free to ask another question anytime.",
]

_BYE_REPLIES = [
    "Take care! Come back anytime you need risk data or guidance.",
    "Goodbye — stay safe.",
]

_ACK_REPLIES = [
    "Got it. Anything else you'd like to check?",
    "Sounds good — let me know what else you need.",
]


def _general_chat_answer(question: str) -> dict:
    """Instant, deterministic small-talk reply — no DB lookup, no RAG
    retrieval, no LLM call. Greetings and casual chat ("hii", "thanks",
    "bye", "ok") should never fall through to "insufficient data" or wait
    on an LLM round-trip; they get a friendly canned reply immediately."""
    q = question.strip().lower()
    if any(w in q for w in ("thank", "thanks", "ty", "cheers")):
        pool = _THANKS_REPLIES
    elif any(w in q for w in ("bye", "goodbye", "see you", "see ya", "cya")):
        pool = _BYE_REPLIES
    elif any(w in q for w in ("ok", "okay", "cool", "nice", "great", "got it", "alright")):
        pool = _ACK_REPLIES
    else:
        pool = _GREETING_REPLIES
    return {
        "answer": random.choice(pool),
        "sources": [],
        "llm_used": False,
        "provider": "none",
        "fallback_reason": None,
        "answer_type": "general_chat",
        "structured_rows": [],
        "query_description": None,
        "llm_comparison": None,
    }


_ABOUT_APP_ANSWER = (
    "This is TerraGuard NER — an AI-based landslide early-warning and risk-monitoring system "
    "for 8 North-East Indian states (built for SIH26001). It combines a machine-learning risk "
    "engine, real historical/rainfall/census data in an Excel-backed in-memory data store, and a RAG assistant (this chat) "
    "for SOP and evacuation guidance. Backend version 1.0.0."
)


def _about_app_answer() -> dict:
    """Instant, fixed answer for "what is this app / who are you / your
    name" style questions. Never guessed by an LLM and never routed through
    the knowledge-base similarity search — the app's own identity is a fact
    TerraGuard already knows about itself, not something to retrieve or
    infer."""
    return {
        "answer": _ABOUT_APP_ANSWER,
        "sources": [],
        "llm_used": False,
        "provider": "none",
        "fallback_reason": None,
        "answer_type": "about_app",
        "structured_rows": [],
        "query_description": None,
        "llm_comparison": None,
    }


def _document_answer(store: Store, question: str, top_k: int) -> dict:
    """Pure RAG path (no structured-data component). Returns the same shape
    answer_query() has always returned, plus answer_type."""
    try:
        results = similarity_search(store, question, top_k)
    except Exception as exc:  # noqa: BLE001 — RAG must fail gracefully, not crash the API
        return {
            "answer": (
                "The knowledge base is not available right now (RAG retrieval failed). "
                "Please verify dataset/terraguard_data.xlsx is present and knowledge_base/ has been "
                "ingested via `python scripts/ingest_knowledge.py`."
            ),
            "sources": [],
            "llm_used": False,
            "provider": "none",
            "fallback_reason": str(exc),
            "answer_type": "insufficient_data",
            "structured_rows": [],
            "query_description": None,
            "llm_comparison": None,
        }

    threshold = _min_adequate_similarity()
    # Only chunks that individually clear the threshold are ever shown or
    # used — the old check only looked at the group's max similarity, which
    # let weak/irrelevant chunks (e.g. an 8% match riding along with a 35%
    # one) still get displayed as if they were supporting evidence.
    adequate_results = [r for r in results if r["similarity"] >= threshold]

    if not adequate_results:
        general = _general_knowledge_answer(question)
        if general is not None:
            return general
        return {
            "answer": (
                "TerraGuard's knowledge base does not contain enough information to answer this "
                "question confidently. Please consult official SOPs directly, or ingest additional "
                "guidance documents into knowledge_base/ and re-run the ingestion script."
            ),
            "sources": [],
            "llm_used": False,
            "provider": "none",
            "fallback_reason": "no_adequate_source",
            "answer_type": "insufficient_data",
            "structured_rows": [],
            "query_description": None,
            "llm_comparison": None,
        }

    results = adequate_results
    sources = _sources_from_results(results)

    if is_llm_configured():
        try:
            answer, provider_used, comparison = generate_answer_with_provider_and_comparison(
                question, [r["content"] for r in results]
            )
            if _llm_declined_to_answer(answer):
                # The model itself says the retrieved context doesn't answer
                # this question — show the clean "insufficient data" state
                # (matching the DB-lookup path's behavior) instead of a
                # "found it" badge over a source dump that didn't actually help.
                return {
                    "answer": (
                        "TerraGuard's knowledge base does not contain a direct answer to this "
                        "question. Please consult official SOPs directly, or ingest additional "
                        "guidance documents into knowledge_base/ and re-run the ingestion script."
                    ),
                    "sources": [],
                    "llm_used": True,
                    "provider": provider_used,
                    "fallback_reason": "llm_declined_insufficient_context",
                    "answer_type": "insufficient_data",
                    "structured_rows": [],
                    "query_description": None,
                    "llm_comparison": comparison,
                }
            return {
                "answer": answer, "sources": sources, "llm_used": True, "provider": provider_used,
                "fallback_reason": None, "answer_type": "document", "structured_rows": [], "query_description": None,
                "llm_comparison": comparison,
            }
        except LLMUnavailable as exc:
            fallback_reason = str(exc)
            # The in-context explanation attempt itself failed (e.g. every
            # configured provider errored or was rejected by the
            # groundedness check for THIS specific prompt) even though
            # relevant sources were found — before ever falling back to a
            # raw chunk dump, retry through the SAME already-configured
            # multi-provider chain's general-knowledge path (still clearly
            # labeled as general knowledge, never presented as a verified
            # TerraGuard record). This is the "reuse the existing LLM
            # config as a fallback" behavior, applied even when the first
            # attempt at using it also failed, so a transient failure on
            # one specific prompt doesn't degrade all the way to raw text.
            general = _general_knowledge_answer(question)
            if general is not None:
                general["fallback_reason"] = f"llm_explain_failed_used_general_knowledge: {fallback_reason}"
                return general
    else:
        fallback_reason = "No LLM provider configured (set LLM_PROVIDER + LLM_API_KEY, or run Ollama, for grounded generation)."

    # Last-resort graceful fallback ONLY: every configured LLM attempt (both
    # the in-context explanation and, if applicable, the general-knowledge
    # retry above) failed, or no LLM is configured at all. Show the
    # retrieved excerpts directly rather than nothing, but label this
    # honestly — "No LLM configured" is only true in the second case, never
    # printed when a provider actually was configured but failed.
    extract = "\n\n".join(f"- {_clean_excerpt(r['content'], max_chars=300)}" for r in results[:3])
    if is_llm_configured():
        answer = (
            f"[AI explanation unavailable right now ({fallback_reason}) — "
            f"showing the most relevant source excerpts instead]\n\n{extract}"
        )
    else:
        answer = f"[No LLM configured — showing retrieved source excerpts directly]\n\n{extract}"
    return {
        "answer": answer, "sources": sources, "llm_used": False, "provider": "none",
        "fallback_reason": fallback_reason, "answer_type": "document", "structured_rows": [], "query_description": None,
        "llm_comparison": None,
    }


_STRUCTURED_EXPLAIN_PROMPT = (
    "You are TerraGuard's assistant. Below is a factual summary computed directly from "
    "TerraGuard's records — every number in it is already correct and final. Rephrase it "
    "into a clear, natural-language answer to the user's question. Do NOT add, change, guess, "
    "or invent any number, location, date, or statistic that is not already present in the "
    "summary below. If the summary says information is unavailable, say so plainly — do not "
    "try to fill the gap yourself.\n\n"
    "User question: {question}\n\n"
    "Computed factual summary:\n{summary}\n\n"
    "Additional supporting document excerpts (for context only, optional):\n{docs}"
)


def answer_query(store: Store, question: str, top_k: int = 4) -> dict:
    """Hybrid entry point: classifies the question, then routes to a real SQL
    lookup (structured), RAG over knowledge_base/ (document), or both
    (combined). Structured numbers ALWAYS come from SQL — the LLM is only
    ever asked to explain them, never to produce them."""
    qtype = query_router.classify_question(question)

    if qtype == "general_chat":
        return _general_chat_answer(question)
    if qtype == "about_app":
        return _about_app_answer()

    if qtype == "document":
        return _document_answer(store, question, top_k)

    # "structured" or "combined": run the real database query first.
    try:
        struct_result = query_router.structured_query(store, question)
    except Exception as exc:  # noqa: BLE001 — a bad structured lookup must fall back, not crash
        logger.warning("structured_query failed, falling back to document search: %s", exc)
        struct_result = {"found": False, "summary": "", "rows": [], "query_description": "structured lookup failed"}

    if not struct_result.get("found"):
        if qtype == "structured":
            # A purely structured question (e.g. "how many landslides in X")
            # with no match is simply "no data" — no document search applies.
            if struct_result.get("summary"):
                return {
                    "answer": struct_result["summary"],
                    "sources": [],
                    "llm_used": False,
                    "provider": "none",
                    "fallback_reason": "structured_no_match",
                    "answer_type": "insufficient_data",
                    "structured_rows": struct_result.get("rows", []),
                    "query_description": struct_result.get("query_description"),
                    "llm_comparison": None,
                }
            return _document_answer(store, question, top_k)

        # An "authoritative" refusal (e.g. "slope isn't tracked") is the
        # honest answer regardless of what the document search turns up —
        # general guidance text is not a substitute for a specific value
        # TerraGuard's database simply does not have.
        if struct_result.get("authoritative") and struct_result.get("summary"):
            return {
                "answer": struct_result["summary"],
                "sources": [],
                "llm_used": False,
                "provider": "none",
                "fallback_reason": "structured_no_match",
                "answer_type": "insufficient_data",
                "structured_rows": struct_result.get("rows", []),
                "query_description": struct_result.get("query_description"),
                "llm_comparison": None,
            }

        # Otherwise (e.g. the question mentions "rainfall" but is really
        # asking for guidance, not a specific record) — try the document
        # half before giving up, so a generic "please specify a location"
        # doesn't shadow a real answer that the knowledge base actually has.
        doc_answer = _document_answer(store, question, top_k)
        if doc_answer["answer_type"] != "insufficient_data":
            return doc_answer
        # Neither half found anything — prefer whichever message is more
        # specific (a real refusal, e.g. "slope isn't tracked") over the
        # generic "knowledge base doesn't cover this" message.
        if struct_result.get("summary"):
            return {
                "answer": struct_result["summary"],
                "sources": doc_answer["sources"],
                "llm_used": False,
                "provider": "none",
                "fallback_reason": "structured_no_match",
                "answer_type": "insufficient_data",
                "structured_rows": struct_result.get("rows", []),
                "query_description": struct_result.get("query_description"),
                "llm_comparison": None,
            }
        return doc_answer

    if qtype == "structured":
        summary = struct_result["summary"]
        answer_text = summary
        llm_used = False
        provider = "none"
        fallback_reason = "No LLM provider configured — showing the computed data summary directly."
        comparison = None
        if is_llm_configured():
            try:
                answer_text, provider, comparison = generate_answer_with_provider_and_comparison(
                    question,
                    [_STRUCTURED_EXPLAIN_PROMPT.format(question=question, summary=summary, docs="(none)")],
                )
                llm_used = True
                fallback_reason = None
            except LLMUnavailable as exc:
                answer_text = summary
                fallback_reason = str(exc)
        return {
            "answer": answer_text,
            "sources": [],
            "llm_used": llm_used,
            "provider": provider,
            "fallback_reason": fallback_reason,
            "answer_type": "structured",
            "structured_rows": struct_result.get("rows", []),
            "query_description": struct_result.get("query_description"),
            "chart_data": struct_result.get("chart_data"),
            "llm_comparison": comparison,
        }

    # "combined": merge structured facts with document retrieval.
    try:
        doc_results = similarity_search(store, question, top_k)
    except Exception:  # noqa: BLE001
        doc_results = []
    adequate_docs = [r for r in doc_results if r["similarity"] >= _min_adequate_similarity()]
    sources = _sources_from_results(adequate_docs)

    summary = struct_result["summary"]
    llm_used = False
    provider = "none"
    fallback_reason = "No LLM provider configured — showing the computed data summary directly."
    answer_text = summary
    if adequate_docs:
        answer_text += "\n\nRelated guidance:\n" + "\n".join(f"- {_clean_excerpt(r['content'], max_chars=300)}" for r in adequate_docs[:2])

    comparison = None
    if is_llm_configured():
        try:
            docs_text = "\n\n".join(r["content"] for r in adequate_docs) or "(none)"
            answer_text, provider, comparison = generate_answer_with_provider_and_comparison(
                question,
                [_STRUCTURED_EXPLAIN_PROMPT.format(question=question, summary=summary, docs=docs_text)],
            )
            llm_used = True
            fallback_reason = None
        except LLMUnavailable as exc:
            fallback_reason = str(exc)

    return {
        "answer": answer_text,
        "sources": sources,
        "llm_used": llm_used,
        "provider": provider,
        "fallback_reason": fallback_reason,
        "answer_type": "combined",
        "structured_rows": struct_result.get("rows", []),
        "query_description": struct_result.get("query_description"),
        "chart_data": struct_result.get("chart_data"),
        "llm_comparison": comparison,
    }
