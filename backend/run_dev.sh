#!/usr/bin/env bash
# Starts the backend with --reload watching ONLY app/ — never .venv/ (which
# has 20,000+ files whose timestamps get touched by OS file indexing,
# causing --reload to see "changes" constantly and restart in a loop).
# --reload-dir alone has been observed to still let WatchFiles pick up
# changes deep inside .venv's installed packages (seen with sympy) on some
# uvicorn/watchfiles versions, so --reload-exclude is added as a second,
# explicit belt-and-suspenders guard rather than relying on --reload-dir
# scoping alone.
cd "$(dirname "$0")"
uvicorn app.main:app --reload --reload-dir app \
  --reload-exclude ".venv/*" --reload-exclude "**/__pycache__/*" \
  --host 0.0.0.0 --port 8000
