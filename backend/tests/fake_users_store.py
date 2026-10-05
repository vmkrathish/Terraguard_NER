"""In-memory stand-in for `app.core.supabase_users.SupabaseUsersStore`, used
ONLY by the test suite (see conftest.py's dependency override).

Authentication now depends on a real Supabase project — tests deliberately
do NOT call it: hitting a live project on every CI/local test run would be
slow, network-dependent, and would create/mutate real account rows in the
user's actual Supabase project on every run. This fake implements the exact
same `UsersStore` interface `auth.py`/`deps.py` depend on, seeded with the
same three demo accounts (same emails/passwords) the Excel `users` sheet
used to seed, so every existing auth test keeps exercising the same
scenarios without any change to their expectations."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Optional

import bcrypt

from app.core.supabase_users import UsersStore


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class FakeUsersStore(UsersStore):
    def __init__(self):
        now = _now_iso()
        seed = [
            {"email": "admin@terraguard.demo", "password_hash": _hash("Admin@123"),
             "full_name": "Demo Admin", "role": "admin"},
            {"email": "authority@terraguard.demo", "password_hash": _hash("Authority@123"),
             "full_name": "Demo District Authority", "role": "authority"},
            {"email": "field@terraguard.demo", "password_hash": _hash("Field@123"),
             "full_name": "Demo Field Officer", "role": "field_officer"},
            # The protected Super Admin — matches app.core.config.Settings's
            # default SUPER_ADMIN_EMAIL, so `_is_super_admin()` recognizes it
            # in tests exactly like it would against the real Supabase table.
            {"email": "admin.terraguard@gmail.com", "password_hash": _hash("SuperAdmin@123"),
             "full_name": "Super Admin", "role": "admin"},
        ]
        self._rows: dict[str, dict[str, Any]] = {}
        for row in seed:
            user_id = str(uuid.uuid4())
            self._rows[user_id] = {
                "id": user_id,
                "is_active": True,
                "last_seen": None,
                "created_at": now,
                "updated_at": now,
                "reset_token": None,
                "reset_token_expires": None,
                **row,
            }

    def get_by_email(self, email: str) -> Optional[dict[str, Any]]:
        for row in self._rows.values():
            if row["email"] == email:
                return dict(row)
        return None

    def get_by_id(self, user_id: str) -> Optional[dict[str, Any]]:
        row = self._rows.get(user_id)
        return dict(row) if row else None

    def get_by_reset_token(self, token: str) -> Optional[dict[str, Any]]:
        for row in self._rows.values():
            if row.get("reset_token") == token:
                return dict(row)
        return None

    def list_active(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows.values() if row["is_active"]]

    def list_all(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows.values()]

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        user_id = str(uuid.uuid4())
        now = _now_iso()
        full_row = {
            "id": user_id, "last_seen": None, "created_at": now, "updated_at": now,
            "reset_token": None, "reset_token_expires": None, **row,
        }
        self._rows[user_id] = full_row
        return dict(full_row)

    def update_by_id(self, user_id: str, updates: dict[str, Any]) -> bool:
        row = self._rows.get(user_id)
        if not row:
            return False
        row.update(updates)
        return True
