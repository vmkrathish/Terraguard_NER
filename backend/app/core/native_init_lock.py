"""
Process-wide lock guarding the first-time native-library initialization of
XGBoost (risk_engine._load_artifacts) and PyTorch/sentence-transformers
(embeddings._get_bge_model).

Both bundle their own copy of the OpenMP runtime (libomp on macOS).
KMP_DUPLICATE_LIB_OK=TRUE (set at the very top of app/main.py) stops that
runtime from aborting the process when both libraries end up loaded into
the same process — but it does NOT make the two libraries' native
initialization code thread-safe against each other. If the background
embedding-preload thread (started at app startup, see main.py) and a
request thread triggering the *first* /risk/predict call happen to
initialize their respective native libraries at the same literal moment,
the result can be a hard segmentation fault instead of a clean, recoverable
error.

This is exactly what running the backend's pytest suite hits and manual
clicking-through the UI mostly doesn't: pytest calls /risk/predict within
milliseconds of app startup (test_risk.py is often one of the first test
files collected), which is a far tighter race window than a human opening
the dashboard, reading it for a few seconds, and then clicking Predict —
by which point the background preload thread has usually already finished.

Holding this lock around each library's first (cold) load serializes those
two specific critical sections so they can never overlap. Every call after
the first is just an uncontended lock acquire/release (a few hundred
nanoseconds) around an already-cached object, so this has no measurable
effect on steady-state request latency.

(XGBoost was briefly removed from this project, then reinstated after a
direct model comparison favored it on most metrics — this lock is back in
active use on the risk_engine side, not just for embeddings.)
"""
import threading

NATIVE_INIT_LOCK = threading.Lock()
