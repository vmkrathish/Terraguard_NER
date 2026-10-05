import os

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.excel_store import check_store_ready
from app.services.llm_providers import configured_chain_providers, configured_chat_chain, is_llm_configured
from app.services.embeddings import embedding_status

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def health():
    store_ok, store_message = check_store_ready()
    model_path = os.path.join(settings.MODEL_DIR, "risk_model.joblib")
    model_ok = os.path.exists(model_path)

    status = "ok" if (store_ok and model_ok) else "degraded"
    return {
        "status": status,
        # No database anymore — this reports the Excel-backed in-memory
        # data store's readiness. Frontend reads this key, not "database".
        "data_store": {"backend": "excel", "ready": store_ok, "detail": store_message},
        "ml_model": {"ready": model_ok, "path": model_path},
        "llm_configured": is_llm_configured(),
        "llm_provider": settings.LLM_PROVIDER,
        "llm_provider_chain": configured_chain_providers() if settings.LLM_PROVIDER == "multi" else None,
        # What the chatbot will ACTUALLY call, in order (Groq, then
        # OpenRouter only as fallback) — Gemini is never included here even
        # if it has a key and appears in llm_provider_chain above.
        "llm_chat_chain": configured_chat_chain() if settings.LLM_PROVIDER == "multi" else None,
        "routing_engine": "local_road_graph",
        "embeddings": embedding_status(),
        "environment": settings.ENVIRONMENT,
    }
