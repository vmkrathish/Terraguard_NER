import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# --- Point the Excel store at disposable temp-file copies BEFORE app.main
# (and anything it imports) ever calls get_store(), so tests never read or
# write the real project workbooks in dataset/. A temp copy of the real
# SIH26001_Master_Dataset.xlsx is used (read-only in the app anyway) so
# census tests exercise real data; the live-tables workbook is NOT copied
# from the real one — it starts fresh (auto-seeded with the same demo data
# real runs start with) so tests never mutate the project's live file. ---
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_REAL_CENSUS_XLSX = os.path.join(_REPO_ROOT, "dataset", "SIH26001_Master_Dataset.xlsx")
_REAL_LIVE_XLSX = os.path.join(_REPO_ROOT, "dataset", "terraguard_data.xlsx")

_TMP_DIR = tempfile.mkdtemp(prefix="terraguard_test_")
_TEST_LIVE_XLSX = os.path.join(_TMP_DIR, "terraguard_data.xlsx")
_TEST_CENSUS_XLSX = os.path.join(_TMP_DIR, "SIH26001_Master_Dataset.xlsx")

if os.path.exists(_REAL_CENSUS_XLSX):
    shutil.copyfile(_REAL_CENSUS_XLSX, _TEST_CENSUS_XLSX)

# If the real live-data workbook already exists (e.g. scripts/load_historical_data.py
# has been run), start tests from a COPY of it, so tests exercise real
# historical landslide/rainfall rows instead of an empty table — but a copy,
# so tests never write back into the real project file.
if os.path.exists(_REAL_LIVE_XLSX):
    shutil.copyfile(_REAL_LIVE_XLSX, _TEST_LIVE_XLSX)

os.environ["TERRAGUARD_LIVE_XLSX"] = _TEST_LIVE_XLSX
os.environ["TERRAGUARD_CENSUS_XLSX"] = _TEST_CENSUS_XLSX

# --- Same test-isolation reasoning as the two xlsx paths above, applied to
# the LLM provider: several RAG tests (tests/test_rag.py) assert
# `llm_used is False` on the assumption that no real LLM is configured in
# the test environment. That assumption held only by accident, because it
# depended on whatever LLM_PROVIDER happened to be unset/unreachable in
# whichever .env the suite was run against — it silently broke the moment a
# real LLM_PROVIDER (e.g. "multi", with real Groq/Gemini/OpenRouter keys)
# was configured for actual day-to-day use of the app. Force it explicitly
# instead of hoping the developer's real .env cooperates: "none" is a real,
# supported value (see app/core/config.py's LLM_PROVIDER comment and
# app/services/llm_providers.py's is_llm_configured(), which returns False
# for any value other than "ollama"/"multi"/"openai"/"anthropic"), not a
# test-only hack — this makes the RAG fallback path's tests exercise the
# same code path a real "no LLM configured" deployment would.
os.environ["LLM_PROVIDER"] = "none"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.supabase_users import get_users_store  # noqa: E402
from app.main import app  # noqa: E402
from tests.fake_users_store import FakeUsersStore  # noqa: E402

# --- Authentication now depends on a real Supabase project (see
# app/core/supabase_users.py) — tests override that one FastAPI dependency
# with an in-memory fake (same interface, same seeded demo accounts)
# instead of making real network calls to a live Supabase project on every
# test run. Every other endpoint/table is untouched and still goes through
# the real Excel-backed Store above. ---------------------------------------
_fake_users_store = FakeUsersStore()
app.dependency_overrides[get_users_store] = lambda: _fake_users_store


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def users_store():
    return _fake_users_store


@pytest.fixture
def make_user(users_store):
    """Test helper that inserts a fresh account directly into the fake
    users store (bypassing the permission-gated POST /auth/users endpoint,
    which has its own dedicated tests in test_account_management.py) and
    logs it in for a token — used by tests that just need *some*
    already-existing account of a given role, not a test of account
    creation itself."""
    import uuid

    import bcrypt

    def _make(role: str = "field_officer", password: str = "Str0ng!Pass1", **overrides):
        email = overrides.pop("email", f"test.{role}.{uuid.uuid4().hex}@terraguard.demo")
        full_name = overrides.pop("full_name", f"Test {role.replace('_', ' ').title()}")
        row = {
            "email": email,
            "password_hash": bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            "full_name": full_name,
            "role": role,
            "is_active": overrides.pop("is_active", True),
            **overrides,
        }
        inserted = users_store.insert(row)
        return {"email": email, "password": password, "full_name": full_name, "role": role, **inserted}

    return _make


@pytest.fixture(scope="session")
def store():
    from app.core.excel_store import get_store

    return get_store()


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP_DIR, ignore_errors=True)
