"""User-authentication data store — Supabase-backed.

SCOPE: this module is deliberately the ONLY place that talks to Supabase in
this project. Every other feature (landslides, rainfall, risk zones, alerts,
field reports, roads, villages, hospitals, schools, RAG, data-source cache,
alert lifecycle/acknowledgements/assignments) continues to read and write
`dataset/terraguard_data.xlsx` exactly as before, through `excel_store.py` —
completely untouched by this migration. Only the `users` table's
authentication role moved from that workbook's `users` sheet to a real
Supabase Postgres table. The `users` sheet itself is left physically in
place in the workbook (see `excel_store.py`'s `LIVE_TABLES`) as an unused
historical snapshot — nothing in this file reads or writes it.

Talks to Supabase over its auto-generated PostgREST REST API
(`{SUPABASE_URL}/rest/v1/users`) using the service-role secret key, which
must ONLY ever live in this backend process's environment (`backend/.env`,
gitignored) — never in React, Flutter, or any file that leaves this
backend. The secret key bypasses Row Level Security by design, which is
exactly why the `users` table's RLS should be left ON with zero policies
(see `docs/supabase_users_schema.sql`): the anon/publishable key can then
never read or write it at all, and only this backend (holding the secret
key) can.

`UsersStore` is an abstract interface, not just for style: `backend/tests/`
overrides it with an in-memory fake (see `conftest.py`) so the test suite
never makes real network calls to a live Supabase project or mutates real
account data on every CI run. `auth.py`/`deps.py` depend on the interface
via `get_users_store()`, not on `SupabaseUsersStore` directly, so that
override is a single FastAPI dependency swap.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class UsersStore(ABC):
    """Everything `auth.py`/`deps.py` need from a user-authentication data
    source. `SupabaseUsersStore` below is the real implementation; tests use
    an in-memory fake implementing the same interface."""

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[dict[str, Any]]:
        ...

    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        ...

    @abstractmethod
    def get_by_reset_token(self, token: str) -> Optional[dict[str, Any]]:
        ...

    @abstractmethod
    def list_active(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def list_all(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    def update_by_id(self, user_id: str, updates: dict[str, Any]) -> bool:
        ...


class SupabaseUsersStore(UsersStore):
    """Talks to a Supabase Postgres `users` table over PostgREST. Any
    network failure or non-2xx response becomes a real
    `HTTPException(503)` — never a silent fallback and never a fabricated
    success — since authentication has no other data source to fall back
    to now that this is the only place `users` is read/written."""

    def __init__(self, base_url: str, secret_key: str, timeout_seconds: float = 10.0):
        self._client = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/rest/v1",
            headers={
                "apikey": secret_key,
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout_seconds,
        )

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable. Please try again shortly.",
            ) from exc
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable. Please try again shortly.",
            )
        return resp

    def get_by_email(self, email: str) -> Optional[dict[str, Any]]:
        resp = self._request("GET", "/users", params={"email": f"eq.{email}", "select": "*", "limit": 1})
        rows = resp.json()
        return rows[0] if rows else None

    def get_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        resp = self._request("GET", "/users", params={"id": f"eq.{user_id}", "select": "*", "limit": 1})
        rows = resp.json()
        return rows[0] if rows else None

    def get_by_reset_token(self, token: str) -> Optional[dict[str, Any]]:
        resp = self._request("GET", "/users", params={"reset_token": f"eq.{token}", "select": "*", "limit": 1})
        rows = resp.json()
        return rows[0] if rows else None

    def list_active(self) -> list[dict[str, Any]]:
        resp = self._request(
            "GET", "/users", params={"is_active": "eq.true", "select": "id,full_name,email,role"}
        )
        return resp.json()

    def list_all(self) -> list[dict[str, Any]]:
        """Every account, active or not — used by the Account Management
        screens (unlike `list_active()`, used by the unrelated
        Assign-Response picker) so an admin/authority can also see and
        reactivate a deactivated account, not just active ones."""
        resp = self._request(
            "GET", "/users", params={"select": "id,full_name,email,role,is_active,created_at,last_seen"}
        )
        return resp.json()

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        resp = self._request(
            "POST", "/users", json=row, headers={"Prefer": "return=representation"}
        )
        rows = resp.json()
        return rows[0]

    def update_by_id(self, user_id: str, updates: dict[str, Any]) -> bool:
        resp = self._request(
            "PATCH", "/users", params={"id": f"eq.{user_id}"}, json=updates,
            headers={"Prefer": "return=representation"},
        )
        return len(resp.json()) > 0


@lru_cache
def get_users_store() -> UsersStore:
    """FastAPI dependency — a process-wide singleton `SupabaseUsersStore`
    built from `SUPABASE_URL`/`SUPABASE_SECRET_KEY` (backend/.env only,
    never shipped to React/Flutter). Raises immediately with a clear error
    if either is unset, rather than silently falling back to Excel or
    fabricating a store that always fails — misconfiguration should be loud
    at startup/first-request, not a mysterious downstream 401."""
    settings = get_settings()
    if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication is not configured on this server (SUPABASE_URL / "
                "SUPABASE_SECRET_KEY missing from backend/.env)."
            ),
        )
    return SupabaseUsersStore(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY)
