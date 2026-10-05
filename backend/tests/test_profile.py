"""Profile view/edit/change-password — PATCH /auth/profile, POST
/auth/change-password. Each test creates its own fresh account directly in
the fake store (rather than mutating the shared seeded admin account, and
rather than going through the permission-gated POST /auth/users, which has
its own dedicated tests in test_account_management.py) so tests don't
interfere with each other or with test_auth.py's assumptions about the seed
data."""
import uuid


def _signup(client, make_user, **overrides):
    role = overrides.pop("role", "field_officer")
    password = overrides.pop("password", "Str0ng!Pass1")
    user = make_user(role=role, password=password, full_name=overrides.pop("full_name", "Profile Test User"), **overrides)
    login_resp = client.post("/auth/login", json={"email": user["email"], "password": password})
    assert login_resp.status_code == 200, login_resp.text
    payload = {"full_name": user["full_name"], "email": user["email"], "password": password, "role": role}
    body = login_resp.json()
    body["id"] = user["id"]
    return payload, body


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_me_includes_profile_fields(client, make_user):
    _payload, signup_body = _signup(client, make_user)
    resp = client.get("/auth/me", headers=_auth_header(signup_body["access_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == signup_body["email"]
    assert body["role"] == "field_officer"
    assert body["is_active"] is True
    assert "id" in body and body["id"]
    assert "created_at" in body


def test_update_profile_requires_auth(client, make_user):
    resp = client.patch("/auth/profile", json={"full_name": "Nope"})
    assert resp.status_code == 401


def test_update_full_name(client, make_user):
    _payload, signup_body = _signup(client, make_user)
    token = signup_body["access_token"]
    resp = client.patch("/auth/profile", json={"full_name": "Updated Name"}, headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"

    # Reflected immediately on /auth/me with the SAME token — no re-login
    # needed for a name-only change.
    me = client.get("/auth/me", headers=_auth_header(token)).json()
    assert me["full_name"] == "Updated Name"


def test_update_email_success_reissues_token_and_session_stays_valid(client, make_user):
    _payload, signup_body = _signup(client, make_user)
    old_token = signup_body["access_token"]
    new_email = f"changed.{uuid.uuid4().hex}@terraguard.demo"

    resp = client.patch("/auth/profile", json={"email": new_email}, headers=_auth_header(old_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == new_email
    # A changed email invalidates the OLD token's `sub` claim, so a fresh
    # one must be issued so the session doesn't just die mid-edit.
    assert body["access_token"]
    new_token = body["access_token"]

    # The old token no longer resolves to any account.
    stale = client.get("/auth/me", headers=_auth_header(old_token))
    assert stale.status_code == 401

    # The new token keeps the session alive, pointed at the new email.
    fresh = client.get("/auth/me", headers=_auth_header(new_token))
    assert fresh.status_code == 200
    assert fresh.json()["email"] == new_email


def test_update_email_blocks_conflict_with_another_account(client, make_user):
    _payload_a, signup_a = _signup(client, make_user)
    payload_b, signup_b = _signup(client, make_user)

    resp = client.patch(
        "/auth/profile", json={"email": payload_b["email"]}, headers=_auth_header(signup_a["access_token"])
    )
    assert resp.status_code == 409


def test_update_email_allows_resubmitting_own_unchanged_email(client, make_user):
    payload, signup_body = _signup(client, make_user)
    resp = client.patch(
        "/auth/profile", json={"email": payload["email"], "full_name": "Still Me"}, headers=_auth_header(signup_body["access_token"])
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"] is None  # unchanged email -> no re-issue needed


def test_update_profile_ignores_role_injection(client, make_user):
    # ROLE SECURITY: even a hand-crafted request naming `role` must never
    # change it — ProfileUpdateRequest has no such field, so FastAPI/Pydantic
    # drops it before the endpoint ever sees it.
    _payload, signup_body = _signup(client, make_user, role="field_officer")
    token = signup_body["access_token"]

    resp = client.patch("/auth/profile", json={"full_name": "Still Field Officer", "role": "admin"}, headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["role"] == "field_officer"

    me = client.get("/auth/me", headers=_auth_header(token)).json()
    assert me["role"] == "field_officer"


def test_change_password_requires_current_password(client, make_user):
    _payload, signup_body = _signup(client, make_user)
    token = signup_body["access_token"]
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "WrongOne1!", "new_password": "NewStrong1!"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 401


def test_change_password_enforces_strength_rule(client, make_user):
    payload, signup_body = _signup(client, make_user)
    token = signup_body["access_token"]
    resp = client.post(
        "/auth/change-password",
        json={"current_password": payload["password"], "new_password": "weak"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 422


def test_change_password_success_and_new_password_works_on_next_login(client, make_user):
    payload, signup_body = _signup(client, make_user)
    token = signup_body["access_token"]
    resp = client.post(
        "/auth/change-password",
        json={"current_password": payload["password"], "new_password": "BrandNew1!"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200

    # Old password no longer works.
    old = client.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert old.status_code == 401

    # New password works.
    new = client.post("/auth/login", json={"email": payload["email"], "password": "BrandNew1!"})
    assert new.status_code == 200


def test_change_password_never_returns_password_hash(client, make_user):
    payload, signup_body = _signup(client, make_user)
    resp = client.post(
        "/auth/change-password",
        json={"current_password": payload["password"], "new_password": "AnotherOne1!"},
        headers=_auth_header(signup_body["access_token"]),
    )
    assert "password_hash" not in resp.json()


def test_super_admin_cannot_change_own_name_or_email(client):
    # The protected Super Admin's identity must stay stable — even it
    # cannot rename or re-email itself through the self-service endpoint.
    login_resp = client.post("/auth/login", json={"email": "admin.terraguard@gmail.com", "password": "SuperAdmin@123"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    resp = client.patch("/auth/profile", json={"full_name": "New Name"}, headers=_auth_header(token))
    assert resp.status_code == 403

    resp2 = client.patch("/auth/profile", json={"email": "someone.else@terraguard.demo"}, headers=_auth_header(token))
    assert resp2.status_code == 403


def test_super_admin_can_still_change_own_password(client):
    login_resp = client.post("/auth/login", json={"email": "admin.terraguard@gmail.com", "password": "SuperAdmin@123"})
    token = login_resp.json()["access_token"]
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "SuperAdmin@123", "new_password": "SuperAdmin@123"},
        headers=_auth_header(token),
    )
    # Re-setting to the same (already strong) password is a harmless no-op
    # from the strength-rule's point of view — this only asserts that
    # change-password itself isn't blocked for the Super Admin the way
    # name/email edits are.
    assert resp.status_code == 200
