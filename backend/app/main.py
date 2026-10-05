# --- macOS crash workaround: MUST be set before xgboost or torch/sentence- ---
# --- transformers get imported anywhere in this process.                  ---
# XGBoost and PyTorch each bundle their own copy of the OpenMP runtime
# (libomp.dylib). On macOS, if both end up loaded in the same process —
# which now always happens here, since the risk model (XGBoost, loaded on
# first /risk/predict) and the RAG embedding model (PyTorch, preloaded at
# startup below) both run in the same backend — the second one to
# initialize aborts the whole Python process with "OMP: Error #15:
# Initializing libomp.dylib, but found libomp.dylib already initialized."
# This is exactly what a native crash looks like from the outside: macOS's
# "Python quit unexpectedly" dialog, with no Python traceback at all.
# KMP_DUPLICATE_LIB_OK=TRUE tells the OpenMP runtime to allow this instead
# of aborting. It's the standard, widely-used workaround for this specific
# XGBoost+PyTorch conflict (both projects' own issue trackers recommend it)
# — the two runtimes doing near-identical work twice costs a little
# redundant memory/threading overhead, but it does not affect the
# correctness of either library's results.
#
# --- Second, distinct crash found from a real macOS crash report --------- #
# KMP_DUPLICATE_LIB_OK=TRUE only stops the *abort-on-duplicate-init* check.
# It does NOT make two independently-loaded OpenMP runtimes safe to run
# concurrently. A user-provided crash report showed THREE separate physical
# copies of libomp.dylib loaded in one process at once (PyTorch's bundled
# copy, scikit-learn's bundled copy, and the Homebrew copy XGBoost links
# against), and the actual segfault (EXC_BAD_ACCESS / SIGSEGV, "Thread 6
# Crashed") happened deep inside OpenMP's own worker-thread machinery
# (__kmp_launch_worker -> __kmp_fork_barrier -> __kmp_hyper_barrier_release
# -> kmp_flag_64::wait -> __kmp_suspend_initialize_thread). The trigger was
# XGBoost's own model deserialization (GBTree::LoadModel ->
# XGBoosterUnserializeFromBuffer, called from joblib.load() inside
# risk_engine._load_artifacts()) internally calling __kmpc_fork_call, which
# spawns/wakes OpenMP worker threads — and those threads collided with
# worker-thread state already set up by the other two libomp.dylib copies
# from PyTorch/scikit-learn.
#
# The standard, documented fix for exactly this signature is to force every
# OpenMP/BLAS runtime in the process down to a single thread. With a team
# size of 1, OpenMP's fork/join model runs the "parallel" region inline on
# the calling thread instead of waking any worker threads at all, so the
# crash-prone worker-thread code paths above are never reached. Because
# this app only ever loads one small model and runs one prediction at a
# time (never a batch/training workload), forcing single-threaded
# BLAS/OpenMP here has no meaningful performance cost.
#
# NOTE: XGBoost was briefly removed from this project (which would have
# eliminated this crash class at its root — one fewer bundled OpenMP
# runtime), then reinstated after a direct model comparison favored it on
# most metrics. This workaround is therefore back in active use, not
# historical — do not remove these env vars while XGBoost is the risk model.
import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    alerts, auth, census, data_sources, geo, health, landslides, map_layers, rag, rainfall,
    reports, risk, route, weather_live,
)
from app.core.config import get_settings
from app.core.excel_store import get_store

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "AI-Based Early Warning and Landslide Risk Monitoring System for the North Eastern Region (NER). "
        "Predict -> Detect -> Assess Impact -> Explain -> Find Safe Route -> Report -> Warn."
    ),
    version="1.0.0",
)


@app.on_event("startup")
def _load_excel_store():
    """Loads every sheet of dataset/terraguard_data.xlsx (+ the read-only
    Census workbook) into the in-memory store BEFORE the server starts
    accepting requests — replaces the old Postgres connection-pool warm-up.
    Raises on failure (a missing/corrupt workbook should fail startup
    loudly, not serve empty data silently)."""
    get_store()


@app.on_event("startup")
def _preload_embedding_model():
    """Starts loading the BGE-M3 embedding model (and downloading it, on
    first run) in a background thread as soon as the server boots, instead
    of on the first /rag/query request. Without this, the very first RAG
    question a user asks after a fresh install silently blocks for however
    long the ~2.3GB one-time download takes, which looks exactly like the
    app being frozen. This way the download happens while the user is
    still looking at the dashboard, not while they're waiting on a chat
    reply. Never blocks server startup itself, and never crashes it if the
    model can't load — embeddings.py's own fallback handles that."""
    from app.services.embeddings import _get_bge_model

    threading.Thread(target=_get_bge_model, daemon=True).start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # See Settings.cors_origin_regex's docstring: in development this also
    # allows any localhost/127.0.0.1 port (None in production), so Flutter
    # Web's random per-run dev port isn't silently CORS-blocked the way a
    # fixed FRONTEND_URL/ADDITIONAL_CORS_ORIGINS entry alone would leave it.
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(risk.router)
app.include_router(rainfall.router)
app.include_router(landslides.router)
app.include_router(map_layers.router)
app.include_router(reports.router)
app.include_router(route.router)
app.include_router(alerts.router)
app.include_router(rag.router)
app.include_router(geo.router)
app.include_router(census.router)
app.include_router(data_sources.router)
app.include_router(weather_live.router)


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "docs": "/docs",
        "health": "/health",
    }
