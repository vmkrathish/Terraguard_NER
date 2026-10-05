import os

from fastapi import APIRouter, Depends

from app.core.excel_store import Store, get_store
from app.services.rag_pipeline import answer_query, ingest_directory, reembed_all_chunks
from app.schemas.schemas import RagIngestResponse, RagQueryRequest, RagQueryResponse, RagReembedResponse

router = APIRouter(prefix="/rag", tags=["rag"])

KNOWLEDGE_BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "knowledge_base")


@router.post("/query", response_model=RagQueryResponse)
def rag_query(payload: RagQueryRequest, store: Store = Depends(get_store)):
    result = answer_query(store, payload.question, payload.top_k)
    return result


@router.post("/ingest", response_model=RagIngestResponse)
def rag_ingest(store: Store = Depends(get_store)):
    if not os.path.isdir(KNOWLEDGE_BASE_DIR):
        return RagIngestResponse(documents_ingested=0, chunks_created=0, skipped=["knowledge_base/ directory not found"])
    result = ingest_directory(store, KNOWLEDGE_BASE_DIR)
    return result


@router.post("/reembed", response_model=RagReembedResponse)
def rag_reembed(store: Store = Depends(get_store)):
    """Recomputes embeddings for every existing chunk with the currently
    configured embedding backend. Use this after changing the embedding
    model/dimension instead of re-ingesting from source files."""
    result = reembed_all_chunks(store)
    return result
