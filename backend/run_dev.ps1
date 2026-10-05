# Starts the backend with --reload watching ONLY app/ — never .venv/ (which
# has 20,000+ files whose timestamps get touched by OS file indexing/AV
# scanning, causing --reload to see "changes" constantly and restart in a loop).
Set-Location $PSScriptRoot
uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
