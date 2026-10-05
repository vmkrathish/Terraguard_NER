import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    APP_NAME: str = "TerraGuard NER"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "dev-insecure-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    # Data layer: an Excel workbook (dataset/terraguard_data.xlsx) is the
    # single source of truth for all live application data — see
    # app/core/excel_store.py. No database connection string is needed.
    # These two overrides exist only so tests can point the store at
    # disposable temp-file copies instead of the real project workbooks.
    TERRAGUARD_LIVE_XLSX: Optional[str] = None
    TERRAGUARD_CENSUS_XLSX: Optional[str] = None

    # Authentication data (users only): a real Supabase Postgres `users`
    # table, NOT the Excel workbook above — see app/core/supabase_users.py.
    # Every other feature/table still lives entirely in the Excel workbook;
    # this is the one deliberate exception, scoped to authentication only.
    # SUPABASE_SECRET_KEY is the service-role key: it bypasses Row Level
    # Security, so it must ONLY ever be set here (backend/.env, gitignored)
    # — never in frontend/mobile source, never committed, never logged.
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SECRET_KEY: Optional[str] = None

    # The one protected "Super Admin" account (account-management feature).
    # Matched case-insensitively against a user's email in app/api/auth.py's
    # `_is_super_admin()`. This account can never be deactivated/modified by
    # anyone else and is the only account allowed to create other Admins —
    # see the docstring above `_can_create_role`/`_can_manage_status` in
    # app/api/auth.py for the full permission model.
    SUPER_ADMIN_EMAIL: str = "admin.terraguard@gmail.com"

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"
    ADDITIONAL_CORS_ORIGINS: str = ""  # comma-separated

    # ML artifacts
    MODEL_DIR: str = os.path.join(os.path.dirname(__file__), "..", "..", "..", "models")

    # Risk level thresholds (0-100), configurable — NOT scientifically validated
    RISK_LOW_MAX: int = 24
    RISK_MODERATE_MAX: int = 49
    RISK_HIGH_MAX: int = 74

    # RAG / LLM provider abstraction
    LLM_PROVIDER: str = "ollama"  # "none" | "openai" | "anthropic" | "ollama" | "multi"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "qwen3:4b"

    # Ollama (free, local, no API key) — used when LLM_PROVIDER=ollama.
    # Requires the Ollama app running locally (https://ollama.com/download)
    # with a model already pulled, e.g. `ollama pull qwen3:4b`.
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # --- Multi-provider free-tier LLM evaluation (LLM_PROVIDER=multi) ----
    # Set LLM_PROVIDER=multi to query every configured provider below
    # CONCURRENTLY for the same question, score each response (groundedness
    # is a hard gate — see _is_grounded in llm_providers.py — then
    # completeness/responsiveness as tie-breakers), and use whichever
    # answer scores highest as the "optimal" one. This is a genuine
    # evaluate-and-compare step, not a fastest-first fallback: every
    # provider with a key set is actually called and actually scored on
    # every request, and the full per-provider comparison (status, timing,
    # score) is returned to the caller/API so it's visible which provider
    # actually won for that answer. Only providers with an API key set are
    # attempted — leave a key blank for any provider you don't want to use.
    LLM_PROVIDER_CHAIN: str = "groq,gemini,openrouter"

    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.8-flash"

    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "nex-agi/nex-n2.5-pro:free"

    # Per-provider request timeout (seconds). The chat chain calls providers
    # SEQUENTIALLY now (Groq, then OpenRouter only if needed — see
    # llm_providers._chat_chain/_evaluate_all_providers), so a slow/hanging
    # provider no longer holds up a request that a fast Groq answer already
    # resolved; this timeout only bounds each individual attempt. Lowered
    # from 20s to 12s to fail over to OpenRouter faster.
    LLM_PROVIDER_TIMEOUT_SECONDS: float = 12.0

    # Embeddings: BAAI/bge-m3 (real semantic embeddings, 1024 dims), loaded
    # locally via sentence-transformers — no API key, runs on CPU. See
    # embeddings.py for the fallback behavior if the model can't load.
    EMBEDDING_PROVIDER: str = "local"  # "local" only — no hosted embedding provider is configured
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024

    # Live data adapters (optional) — legacy generic stubs, superseded by
    # app/services/data_sources/ (see that package's registry.py). Kept for
    # backward compatibility only; not called by the orchestrator.
    IMD_LIVE_RAINFALL_URL: Optional[str] = None
    SATELLITE_API_URL: Optional[str] = None
    SATELLITE_API_KEY: Optional[str] = None

    # --- Data-source adapters (app/services/data_sources/) --------------
    # NASA POWER and ISRIC SoilGrids need no credentials (public APIs) and
    # are always available once network access allows it. The sources below
    # are optional/credentials-gated — leave unset to run without them; the
    # orchestrator falls back gracefully and reports `insufficient_data`
    # rather than fabricating a value.
    IMD_DATA_GOV_IN_RESOURCE_ID: Optional[str] = None
    IMD_DATA_GOV_IN_API_KEY: Optional[str] = None
    COPERNICUS_CLIENT_ID: Optional[str] = None
    COPERNICUS_CLIENT_SECRET: Optional[str] = None
    BHUVAN_API_KEY: Optional[str] = None

    # How long a cached external-source value may be reused before it's
    # considered stale and re-fetched (see data_sources/cache.py).
    DATA_SOURCE_CACHE_RAINFALL_MAX_AGE_MINUTES: int = 180
    DATA_SOURCE_CACHE_SOIL_MAX_AGE_MINUTES: int = 60 * 24 * 30  # soil properties change slowly
    # "Live" current-conditions weather (Open-Meteo) goes stale fast — short
    # cache window so the dashboard carousel reflects genuinely current
    # conditions rather than a climatology-style value.
    DATA_SOURCE_CACHE_LIVE_WEATHER_MAX_AGE_MINUTES: int = 15

    # --- Automatic prediction / monitoring (Mode B) ----------------------
    # Not yet wired to a running scheduler in this version — these are the
    # configuration knobs the orchestrator/feature pipeline already honor
    # for freshness checks, ready for a scheduler to use.
    PREDICTION_INTERVAL_MINUTES: int = 60
    DATA_REFRESH_INTERVAL_MINUTES: int = 180
    ALERT_COOLDOWN_MINUTES: int = 120

    # Firebase Cloud Messaging (optional — alert-history/testing works without it)
    FCM_SERVER_KEY: Optional[str] = None
    FCM_PROJECT_ID: Optional[str] = None

    # Uploads
    MAX_UPLOAD_SIZE_MB: int = 8
    ALLOWED_IMAGE_MIME_TYPES: str = "image/jpeg,image/png,image/webp"
    UPLOAD_DIR: str = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")

    @property
    def cors_origins(self) -> list[str]:
        origins = [self.FRONTEND_URL]
        if self.ADDITIONAL_CORS_ORIGINS:
            origins += [o.strip() for o in self.ADDITIONAL_CORS_ORIGINS.split(",") if o.strip()]
        return origins

    @property
    def cors_origin_regex(self) -> Optional[str]:
        """In development only, additionally allow ANY localhost/127.0.0.1
        port via regex, on top of the exact-match `cors_origins` list above.

        This matters specifically for Flutter Web: `flutter run -d chrome`
        picks a new random local port every time it starts (e.g.
        `http://localhost:59456`), unlike the React frontend's fixed Vite
        port (5173). An exact-match `FRONTEND_URL`/`ADDITIONAL_CORS_ORIGINS`
        origin can never keep up with that, so without this regex every
        Flutter-Web run would be silently CORS-blocked by the browser no
        matter what backend URL it's pointed at. Not enabled outside
        `development` — production should keep an explicit origin allowlist."""
        if self.ENVIRONMENT != "development":
            return None
        return r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    @property
    def allowed_mime_types(self) -> list[str]:
        return [m.strip() for m in self.ALLOWED_IMAGE_MIME_TYPES.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
