# Terraguard_NER — AI-Based Early Warning and Landslide Risk Monitoring
An MVP for landslide risk monitoring in India's North Eastern Region:
**Predict → Detect → Assess Impact → Explain → Find Safe Route → Report → Warn.**

Built on real historical data (NASA COOLR landslide events + IMD district rainfall for 8 NE states) — not synthetic placeholders. Full data audit, sources, and known gaps: `data/README.md`.

## 1. What's in the system

FastAPI backend, a React/Leaflet web dashboard (with separate Field Officer / Authority / Admin dashboard views), and a Flutter mobile app, together covering: a trained ML risk model with explainability, rainfall-anomaly detection, GIS chain-reaction analysis (landslide → road blockage → village isolation), a risk-aware and emergency-type-aware route optimizer, geotagged field reporting with offline sync, AI photo triage, and a RAG disaster-management assistant.

## 2. Features

- Landslide risk prediction (Logistic Regression / Random Forest / XGBoost — best model auto-selected by validation PR-AUC; **XGBoost is currently selected**, after a direct side-by-side comparison against Random Forest — see `FINAL_VALIDATION.md` for the full metrics table)
- Real R²/MAE model evaluation (reported honestly as probability-vs-outcome calibration metrics, since this is a binary classifier, not a regression model) — visible via `GET /risk/model-metrics` and the "Model evaluation" panel on the Prediction page and Admin dashboard
- Monthly rainfall anomaly ("rainfall shock") detection, with district-name-alias handling for pre-2011 IMD district names
- GIS risk heatmap (React + Leaflet + OpenStreetMap) with landslide-event pins colored by real historical severity, and hover/click details (place, what happened, per-district historical event rate)
- Landslide → road blockage → village isolation chain-reaction analysis
- Risk-aware, emergency-type-aware emergency routing: a local road-network graph (NetworkX/Dijkstra over the `roads` table) with blocked-road avoidance, and automatic nearest-safe-zone lookup (hospital-only for medical emergencies, strict all-risk-zone avoidance for rescue/fire) — no external routing service or setup required
- Geotagged field reporting with photo upload and local AI photo triage
- RAG disaster-management assistant (in-process numpy cosine-similarity search over embeddings stored in the Excel workbook + pluggable LLM provider, with a graceful no-key fallback; Ollama's `qwen3` "thinking" mode is disabled and output/context length capped for fast replies). Optional multi-provider free-tier evaluation (Groq / Gemini / OpenRouter, queried concurrently on every question, compared, and the optimal answer selected) as an alternative to Ollama — every provider is still only ever allowed to explain TerraGuard's own retrieved data, verified by an automated groundedness check before an answer is even eligible to be selected (see §8).
- Alert history and testing interface
- Offline field-report queue with idempotent sync (Flutter + SQLite)
- Three role-based dashboards (Field Officer / Authority / Admin), each auto-refreshing when a new HIGH/CRITICAL prediction is made anywhere in the app


---

## 3. Prerequisites — install these first

There is **no database server to install**. All application data — everything
that used to live in PostgreSQL/PostGIS/pgvector — lives in a plain Excel
workbook (`dataset/terraguard_data.xlsx`, auto-created and demo-seeded the
first time the backend starts) plus the bundled, read-only
`dataset/SIH26001_Master_Dataset.xlsx` census workbook. See
`docs/architecture.md` for the full data-layer design.

If your machine already has Python and Node.js set up, skip to **§4 Quick
start**. If not, follow your OS's section below.

You need, regardless of OS:
1. **Python 3.11 or newer** (backend, ML training scripts)
2. **Node.js 18 or newer, with npm** (frontend)
3. **Git** (to clone/manage the project; Windows also needs this for Git Bash, used to run the project's `.sh` scripts)

Optional, only if you want these specific features (a working fallback exists without it — see §8):
4. **Ollama** — only for a free local LLM behind the RAG assistant
5. **Flutter SDK 3.3+** — only for the mobile app (§7)

### 3a. macOS — install prerequisites

Open **Terminal** and run each block in order.

**Homebrew** (if you don't already have it — check with `brew --version` first):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Xcode Command Line Tools** (needed to compile some Python packages' native extensions):
```bash
xcode-select --install
```

**Python, Node, Git:**
```bash
brew install python@3.11 node git
```
Verify each installed correctly:
```bash
python3 --version      # should print 3.11.x or newer
node --version          # should print v18.x or newer
```

That's everything required. Continue to **§4 Quick start → macOS/Linux**.

### 3b. Windows — install prerequisites

Use **PowerShell** for everything below unless a step says otherwise. Run PowerShell as Administrator for the installer steps.

**1. Python 3.11+:**
Download the installer from [python.org/downloads](https://www.python.org/downloads/). During install, **check "Add python.exe to PATH"** before clicking Install — this is the single most common setup mistake on Windows. Verify:
```powershell
python --version
```

**2. Node.js 18+ (LTS):**
Download and run the installer from [nodejs.org](https://nodejs.org/) (choose the LTS version). Verify:
```powershell
node --version
npm --version
```

**3. Git for Windows** (also installs **Git Bash**, which you'll need for this project's `.sh` scripts):
Download from [git-scm.com/download/win](https://git-scm.com/download/win) and run the installer with default options. Verify:
```powershell
git --version
```

**4. Visual Studio Build Tools** (needed only if `pip install` hits a package with no prebuilt Windows wheel — rare with this project's current dependencies, but keep this in your back pocket):
Download the **Build Tools for Visual Studio** installer from [visualstudio.microsoft.com/downloads](https://visualstudio.microsoft.com/downloads/) (scroll to "Tools for Visual Studio"). In the installer, select the **"Desktop development with C++"** workload, then Install.

That's everything required. Continue to **§4 Quick start → Windows (PowerShell)**.

---

## 4. Quick start

Two terminals: **backend** and **frontend**. There is no separate database
terminal/setup step — the backend auto-creates and demo-seeds
`dataset/terraguard_data.xlsx` (users, villages, hospitals, schools, roads,
risk zones) the first time it starts, exactly like `database/seed.sql` used
to. Real historical landslide/rainfall data is loaded into the same
workbook by `scripts/load_historical_data.py` (part of the backend setup
below).

### macOS / Linux

**Terminal 1 — backend (one-time setup):**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env              # then edit backend/.env — see §5

python3 ../scripts/build_master_dataset_v3.py    # builds the real-data training table
python3 ../scripts/preprocess.py                 # builds the feature table + train/test split
python3 ../scripts/train_model.py                # trains and saves the risk model (LR / RF / XGBoost — best auto-selected)
python3 ../scripts/load_historical_data.py       # loads real landslide + rainfall data into dataset/terraguard_data.xlsx
python3 ../scripts/ingest_knowledge.py           # loads the knowledge base for the AI assistant

uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```
The first run auto-creates `dataset/terraguard_data.xlsx` with the same demo
accounts and illustrative sample data (villages, hospitals, schools, roads,
risk zones) `database/seed.sql` used to provide — see `docs/architecture.md`
for the full sheet-per-table layout.
`--reload-dir app` is required, not optional — without it, `--reload` watches the entire `backend/` folder INCLUDING `.venv/` (20,000+ files). OS-level file indexing (Spotlight on macOS, Windows Search/antivirus on Windows) touches those files' timestamps in the background, so `--reload` sees constant "changes" and restarts the server in an infinite loop — the exact symptom if your terminal shows `WatchFiles detected changes in '.venv/lib/...'... Reloading...` over and over. `--reload-dir app` limits watching to your actual source code. A ready-made `backend/run_dev.sh` (macOS/Linux) and `backend/run_dev.ps1` (Windows) run this exact command for you — just `./run_dev.sh` or `.\run_dev.ps1` instead of retyping it. If the reload loop still shows up even though you used the script correctly, it's almost always a leftover backend process from an earlier terminal tab still holding port 8000, not a bug in the script — check with `lsof -i :8000` (macOS/Linux) or `netstat -ano | findstr :8000` (Windows), kill it, and start fresh.

If the shell says `uvicorn: command not found` (venv wasn't actually activated, or `pip install -r requirements.txt` above didn't finish successfully), either re-run `source .venv/bin/activate` first, or bypass PATH entirely with:
```bash
python3 -m uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Backend health check: **http://localhost:8000/health**. API docs: **http://localhost:8000/docs**.

### Windows (PowerShell)

Run any `.sh` script from **Git Bash** (installed in §3b) — PowerShell can't run them directly. Everything else below works in plain PowerShell.

**Terminal 1 — backend (one-time setup):**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example .env            # then edit backend\.env — see §5

python ..\scripts\build_master_dataset_v3.py     # builds the real-data training table
python ..\scripts\preprocess.py                  # builds the feature table + train/test split
python ..\scripts\train_model.py                 # trains and saves the risk model (LR / RF / XGBoost — best auto-selected)
python ..\scripts\load_historical_data.py        # loads real landslide + rainfall data into dataset\terraguard_data.xlsx
python ..\scripts\ingest_knowledge.py            # loads the knowledge base for the AI assistant

uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```
`--reload-dir app` is required — without it, `--reload` watches all of `backend\` including `.venv\` (20,000+ files), and Windows Search/antivirus touching those files' timestamps causes an infinite restart loop (`WatchFiles detected changes in '.venv\lib\...'... Reloading...` repeating forever). Or just run `backend\run_dev.ps1`, which does this for you.

If `.venv\Scripts\activate` is blocked by PowerShell's execution policy, run this once (as Administrator) and try again: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.

**If PowerShell says `uvicorn : The term 'uvicorn' is not recognized...`** — this is the most common Windows-specific snag, so read this even if it looks like a typo error. It means either:
- `.venv\Scripts\activate` was not actually run in **this** PowerShell window (each new terminal tab starts un-activated — you must run `.venv\Scripts\activate` again in every new tab before running backend commands), or
- `pip install -r requirements.txt` above did not fully succeed (scroll up and check for red error text).

The reliable fix that works regardless of PATH/activation state — run this instead, from the same `backend` folder, venv activated:
```powershell
python -m uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```
`python -m uvicorn` calls the exact same server, just via Python's module runner instead of relying on a separate `uvicorn.exe` being on PATH — this always works if `pip install -r requirements.txt` succeeded, even if the plain `uvicorn` command doesn't.

**Terminal 2 — frontend:**
```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Backend health check: **http://localhost:8000/health**. API docs: **http://localhost:8000/docs**.

### Re-running later (both OSes) — the only commands you need after first-time setup

Once §3 and §4's one-time steps are done, **you never repeat prerequisite installs, `pip install`, `npm install`, or model-training** — just start the two services with these commands, every time:

| | macOS/Linux | Windows (PowerShell) |
|---|---|---|
| Backend | `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000` | `cd backend; .venv\Scripts\activate; uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000` |
| Frontend | `cd frontend && npm run dev` | `cd frontend; npm run dev` |

Then open **http://localhost:5173** as before. If `uvicorn` isn't recognized as a command (Windows especially — see the troubleshooting note in §4 above), replace it with `python -m uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000` (macOS/Linux: `python3 -m uvicorn ...`) — same server, just invoked without relying on PATH.

---

## 5. Environment variables

Copy `.env.example` to `backend/.env` and fill in what you need — everything has a working default or graceful fallback, so start with just `SECRET_KEY`. Full variable list and explanations are in `.env.example` itself. Never commit a real `.env` file.

## 6. Common tasks

**Retrain the risk model** (after changing the dataset or wanting to reproduce results — compares Logistic Regression, Random Forest, and XGBoost, and auto-selects the best by validation PR-AUC):
```bash
python scripts/build_master_dataset_v3.py   # macOS/Linux — Windows: python scripts\build_master_dataset_v3.py
python scripts/preprocess.py
python scripts/train_model.py
```
See `data/README.md` for the dataset audit, `FINAL_VALIDATION.md` for the full 3-model comparison table, and `models/model_metadata.json` for the current model's exact metrics.

**Re-ingest or re-embed the knowledge base** (after editing files in `knowledge_base/`, or switching embedding models):
```bash
python scripts/ingest_knowledge.py            # ingest new/changed files
python scripts/ingest_knowledge.py --reembed  # recompute embeddings for everything already ingested
```

**Run tests:**
```bash
cd backend && pytest                # backend — virtualenv active; tests use a disposable temp copy
                                     # of the Excel workbooks, never the real dataset/ files
cd frontend && npm run build        # frontend production build
cd mobile && flutter analyze && flutter test   # mobile — requires Flutter SDK
```

Or run the full project health check at once:
```bash
python scripts/check_environment.py
python scripts/validate_project.py
```

**Validating the Census 2001 village dataset** (optional — exposure/context data only, see `docs/DATASET_SCHEMA_DIFF.md` for the full inspection, schema-diff, and why it never feeds the risk model). There is no separate "ingest" step anymore — `backend/app/core/excel_store.py` reads this workbook's `Master_Dataset` sheet directly, in memory, every time the app starts. This script is a standalone sanity check you can run without starting the server:
```bash
# The Excel file is bundled inside this project at dataset/SIH26001_Master_Dataset.xlsx
# specifically so this works out of the box for anyone you share this project with — no
# separate file to find or re-attach. With no --file, this checks that bundled copy:
python scripts/ingest_village_census.py

# Only pass --file if you want to check a DIFFERENT copy of the workbook (any OS):
python scripts/ingest_village_census.py --file /path/to/SIH26001_Master_Dataset.xlsx
# Windows (PowerShell): python scripts\ingest_village_census.py --file C:\path\to\SIH26001_Master_Dataset.xlsx
```

**External environmental data sources** (NASA POWER, SoilGrids — no API key needed; IMD/Copernicus/Bhuvan are optional and credentials-gated): see `backend/app/services/data_sources/` and `GET /data-sources/status` for what's configured. `GET /rainfall/current?lat=&lon=` and `GET /data-sources/soil?lat=&lon=` go through the acquisition orchestrator (the Excel-backed `data_source_cache` sheet first, then external sources, honestly reporting `insufficient_data` rather than guessing).

## 7. Mobile app (Flutter)

```bash
cd mobile
flutter create . --platforms=android,ios   # first time only
python3 scripts/fix_local_network.py       # first time only — required, see mobile/README.md
flutter pub get
flutter run
```

`fix_local_network.py` is required, not optional: both Android and iOS block plain `http://` traffic by default, and the backend runs on `http://` locally — skip this and the app can't reach the backend. Backend-URL configuration (Android emulator uses `10.0.2.2`, physical devices use your LAN IP or a tunnel): `mobile/README.md`.

## 8. Optional: free local LLM, real routing, and remote access

None of these are required to run the MVP — every feature has a working fallback without them.

### Free local LLM via Ollama

Gives the RAG assistant full generated answers instead of raw retrieved excerpts — no API key, no billing, runs entirely on your machine. Replies are tuned for speed: Ollama's `qwen3` "thinking" mode is disabled and output/context length are capped, so a reply should return in a few seconds, not the 30-80s an unconfigured `qwen3` install would otherwise take.

1. Install [Ollama](https://ollama.com/download).
2. Pull a model sized to your RAM (one-time download):

   | RAM | Command |
   |---|---|
   | 8GB | `ollama pull qwen3:1.7b` |
   | 16GB | `ollama pull qwen3:4b` (default) |
   | 32GB+ | `ollama pull qwen3:8b` |
3. Leave Ollama running in the background.
4. In `backend/.env`: `LLM_PROVIDER=ollama`, `LLM_MODEL=qwen3:4b` (match what you pulled), `OLLAMA_BASE_URL=http://localhost:11434`.
5. Restart the backend. Check `/health` for `llm_configured: true`.

Semantic search for the assistant (BAAI/bge-m3) sets itself up automatically — `pip install -r requirements.txt` installs it, and the ~2.3GB model downloads once on first use, then works offline. Check `/health` → `embeddings.backend`: `bge-m3` means it's active; `hashing_fallback` means it didn't load — the app still works, just with weaker keyword-only matching, until this is fixed. Two known causes: (1) the download didn't complete (no internet on first run — just retry with a connection), or (2) `torch` is older than 2.6 — newer `transformers`/`sentence-transformers` releases refuse to `torch.load` model weights on torch<2.6 (a CVE-2025-32434 safety guard) and silently fall back instead of erroring. `requirements.txt` pins `torch==2.6.0` specifically to avoid this — if you're on an older checked-out copy with `torch==2.5.1` still pinned, upgrade it (`pip install -U torch==2.6.0` inside the activated venv) and restart the backend.

### Multi-provider free-tier LLM evaluation (alternative to Ollama)

Instead of running a local model via Ollama, the RAG assistant can query **three free-tier cloud LLM APIs — Groq, Gemini, and OpenRouter — at the same time, on every question**, then automatically compare their responses and use whichever one is judged optimal. This is a genuine evaluate-and-compare step, not a fastest-first fallback: every configured provider is actually called and actually scored on every request.

| Provider | Model | Free key |
|---|---|---|
| Groq | `openai/gpt-oss-120b` | https://console.groq.com/keys |
| Gemini | `gemini-3.8-flash` | https://aistudio.google.com/apikey |
| OpenRouter | `nex-agi/nex-n2.5-pro:free` (no cost — free-tier models rotate, check openrouter.ai/models?max_price=0 if this stops working) | https://openrouter.ai/keys |

You don't need all three — any provider whose key is left blank is skipped, not attempted. In `backend/.env`:
```
LLM_PROVIDER=multi
LLM_PROVIDER_CHAIN=groq,gemini,openrouter
GROQ_API_KEY=...
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
```
Restart the backend. `/health` will show `llm_provider: "multi"` and `llm_provider_chain` listing which providers actually have a key set right now.

**How the "optimal" answer is chosen:**
1. **Groundedness is a hard gate.** Every response is run through an automated check (`llm_providers._is_grounded`) before it's even eligible: if it contains a number that doesn't appear anywhere in the real retrieved context, it's disqualified outright — this is the safeguard against a free-tier model inventing a plausible-sounding statistic, and it applies no matter how fluent or fast that answer was.
2. **Among the surviving, grounded answers**, a heuristic score (mostly completeness, with responsiveness as a minor tie-breaker) ranks them, and the highest-scoring one is used.
3. The **full comparison — every provider's status, groundedness, response time, and score** — is returned in the API response (`RagQueryResponse.llm_comparison`) and shown in the RAG Assistant UI under each answer, so it's visible which of the three actually won and why, not just which one happened to answer.

Same non-fabrication rule as every other LLM path in this project: every provider is given the same instruction as Ollama — answer ONLY from TerraGuard's retrieved context, and say so explicitly if it's inadequate. `RagQueryResponse.provider` reports which provider's answer was selected as optimal.

**When TerraGuard genuinely has no data on a question** (no matching database row, no matching knowledge-base document), the multi-provider evaluation can optionally answer from its own general disaster-management knowledge instead of returning nothing — but only when `LLM_PROVIDER=multi` is set, and the reply is always returned as `answer_type: "general_knowledge"` with a visible "not a verified TerraGuard record" notice (shown as a distinct amber badge in the RAG Assistant UI). It is never used for anything location-specific (risk scores, predictions, historical counts) — those always come from the ML engine or a real database row, never from this fallback.

### Reaching the backend from a phone or over the internet

Not needed for local use — only for a physical mobile device off your LAN, or a live demo:
```bash
cloudflared tunnel --url http://localhost:8000
```
Set the resulting URL in the mobile app's backend-URL setting, or as `VITE_API_BASE_URL` (frontend) / `ADDITIONAL_CORS_ORIGINS` (backend).

## 9. Demo credentials

Auto-seeded into `dataset/terraguard_data.xlsx`'s `users` sheet the first time the backend runs — demo accounts only, change or remove before any real deployment:

| Role | Email | Password |
|---|---|---|
| Admin | admin@terraguard.demo | Admin@123 |
| District authority | authority@terraguard.demo | Authority@123 |
| Field officer | field@terraguard.demo | Field@123 |

Each role lands on its own dashboard after login (Field Officer / Authority / Admin — see §2). Or create a new account from the **Sign Up** screen (`/signup`). The dashboard is fully behind sign-in; **Forgot Password** (`/forgot-password`) works without an email provider configured — it shows the reset link directly on-screen for testing (wire a real email provider in `backend/app/api/auth.py::forgot_password` before any real deployment).

## 10. Known limitations

- **Only monthly rainfall data exists** — no daily/antecedent (1-day, 3-day, 7-day) rainfall figures until a live daily-resolution feed is connected via `backend/app/services/live_data_adapters.py`.
- **BGE-M3 needs one internet connection, once** — see §8. Falls back automatically to keyword-overlap search if it can't download.
- **The question router for the AI assistant is keyword-based**, not a trained classifier — appropriate for TerraGuard's bounded question categories, but an unusual phrasing can occasionally be misrouted. It always prefers showing nothing (`insufficient_data`) over letting the LLM guess.
- **Flutter app is provided but not build-tested in every environment** — run `flutter analyze`/`flutter test` yourself; see `mobile/README.md`.
- **District name harmonization is best-effort** — the IMD rainfall table uses pre-2011 district names; only a handful of well-known renames are aliased in `backend/app/services/rainfall_shock.py`.
- **Seed data for villages/hospitals/schools/roads is illustrative**, not surveyed government infrastructure — only the landslide events and rainfall records (loaded via `scripts/load_historical_data.py`) are real historical data. Full audit: `data/README.md`.
- **Risk thresholds are configurable defaults**, not scientifically validated bands (`backend/app/core/config.py`).
- **Single-process, single-`uvicorn`-worker only.** The Excel store keeps every table in memory in the one backend process and persists mutations to `dataset/terraguard_data.xlsx` under a `filelock`-guarded atomic write; a second worker process (`--workers > 1`, or multiple gunicorn workers) would hold its own separate in-memory copy that only sees another worker's writes on its own next full reload. Do not run this app multi-worker without adding cross-process cache invalidation first.
- **Excel is not a high-throughput or highly-concurrent write target.** Every mutating request rewrites the entire `terraguard_data.xlsx` workbook (all sheets) on save — fine for this MVP's expected request volume, but not a design that scales to heavy concurrent write load or very large tables (`village_census_profile` alone is ~8,722 rows and loads fine; a live table growing into the hundreds of thousands of rows would need a different persistence layer).

## Project structure

```
terraguard-ner/
  README.md, .gitignore, .env.example
  backend/            FastAPI app, tests, requirements.txt
  frontend/           React + Vite + TypeScript + Leaflet
  mobile/             Flutter app source
  dataset/            SIH26001_Master_Dataset.xlsx (read-only census source),
                       terraguard_data.xlsx (auto-created; single source of
                       truth for all other application data)
  data/               raw/ (real historical data), processed/, metadata/, README.md
  models/             trained model artifacts (risk_model.joblib, etc.)
  knowledge_base/     RAG source documents
  scripts/            build_master_dataset_v3.py, preprocess.py, train_model.py,
                       ingest_knowledge.py, load_historical_data.py,
                       check_environment.py, validate_project.py
  docs/               architecture.md
  FINAL_VALIDATION.md
```
