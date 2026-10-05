"""Account creation, activation/deactivation, and the role-permission
hierarchy behind them (POST /auth/users, GET /auth/users/manageable,
POST /auth/users/{id}/activate|deactivate). Self-registration
(/auth/signup) no longer exists at all — see test_auth.py's
test_signup_endpoint_no_longer_exists.

Uses the four seeded fake-store accounts directly (see
tests/fake_users_store.py): a regular Admin, an Authority, a Field Officer,
and the protected Super Admin (admin.terraguard@gmail.com)."""
import uuid

SUPER_ADMIN_EMAIL = "admin.terraguard@gmail.com"
SUPER_ADMIN_PASSWORD = "SuperAdmin@123"
ADMIN_EMAIL = "admin@terraguard.demo"
ADMIN_PASSWORD = "Admin@123"
AUTHORITY_EMAIL = "authority@terraguard.demo"
AUTHORITY_PASSWORD = "Authority@123"
FIELD_EMAIL = "field@terraguard.demo"
FIELD_PASSWORD = "Field@123"


def _token(client, email, password):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_payload(role, **overrides):
    payload = {
        "full_name": "New Account",
        "email": f"new.{role}.{uuid.uuid4().hex}@terraguard.demo",
        "role": role,
    }
    payload.update(overrides)
    return payload


# ---------- Create-user permission hierarchy ----------

def test_create_user_requires_auth(client):
    resp = client.post("/auth/users", json=_create_payload("field_officer"))
    assert resp.status_code == 401


def test_only_super_admin_can_create_admin(client):
    token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    resp = client.post("/auth/users", json=_create_payload("admin"), headers=_auth(token))
    assert resp.status_code == 403

    super_token = _token(client, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    resp2 = client.post("/auth/users", json=_create_payload("admin"), headers=_auth(super_token))
    assert resp2.status_code == 201
    body = resp2.json()
    assert body["role"] == "admin"
    assert body["initial_password"] == "Terraguard@123"


def test_any_admin_can_create_authority_but_authority_cannot(client):
    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    resp = client.post("/auth/users", json=_create_payload("authority"), headers=_auth(admin_token))
    assert resp.status_code == 201

    authority_token = _token(client, AUTHORITY_EMAIL, AUTHORITY_PASSWORD)
    resp2 = client.post("/auth/users", json=_create_payload("authority"), headers=_auth(authority_token))
    assert resp2.status_code == 403


def test_admin_and_authority_can_create_field_officer_but_field_officer_cannot(client):
    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert client.post("/auth/users", json=_create_payload("field_officer"), headers=_auth(admin_token)).status_code == 201

    authority_token = _token(client, AUTHORITY_EMAIL, AUTHORITY_PASSWORD)
    assert client.post("/auth/users", json=_create_payload("field_officer"), headers=_auth(authority_token)).status_code == 201

    field_token = _token(client, FIELD_EMAIL, FIELD_PASSWORD)
    resp = client.post("/auth/users", json=_create_payload("field_officer"), headers=_auth(field_token))
    assert resp.status_code == 403


def test_create_user_rejects_invalid_role(client):
    token = _token(client, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    resp = client.post("/auth/users", json=_create_payload("superuser"), headers=_auth(token))
    assert resp.status_code == 422


def test_create_user_blocks_duplicate_email(client):
    token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    resp = client.post("/auth/users", json=_create_payload("field_officer", email=ADMIN_EMAIL), headers=_auth(token))
    assert resp.status_code == 409


def test_created_account_can_log_in_with_the_shown_default_password(client):
    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    payload = _create_payload("field_officer")
    create_resp = client.post("/auth/users", json=payload, headers=_auth(admin_token))
    assert create_resp.status_code == 201
    initial_password = create_resp.json()["initial_password"]

    login_resp = client.post("/auth/login", json={"email": payload["email"], "password": initial_password})
    assert login_resp.status_code == 200


# ---------- GET /auth/users/manageable ----------

def test_manageable_users_scoped_by_role(client):
    super_token = _token(client, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    super_list = client.get("/auth/users/manageable", headers=_auth(super_token)).json()
    roles_seen = {row["role"] for row in super_list}
    assert "admin" in roles_seen or "authority" in roles_seen or "field_officer" in roles_seen
    assert all(row["email"] != SUPER_ADMIN_EMAIL for row in super_list)  # never lists itself

    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    admin_list = client.get("/auth/users/manageable", headers=_auth(admin_token)).json()
    assert all(row["role"] in {"authority", "field_officer"} for row in admin_list)

    authority_token = _token(client, AUTHORITY_EMAIL, AUTHORITY_PASSWORD)
    authority_list = client.get("/auth/users/manageable", headers=_auth(authority_token)).json()
    assert all(row["role"] == "field_officer" for row in authority_list)

    field_token = _token(client, FIELD_EMAIL, FIELD_PASSWORD)
    field_list = client.get("/auth/users/manageable", headers=_auth(field_token)).json()
    assert field_list == []


# ---------- Activate/deactivate hierarchy ----------

def test_admin_cannot_deactivate_another_admin(client, make_user):
    other_admin = make_user(role="admin")
    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    resp = client.post(f"/auth/users/{other_admin['id']}/deactivate", headers=_auth(admin_token))
    assert resp.status_code == 403


def test_super_admin_can_deactivate_a_regular_admin(client, make_user):
    other_admin = make_user(role="admin")
    super_token = _token(client, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    resp = client.post(f"/auth/users/{other_admin['id']}/deactivate", headers=_auth(super_token))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_no_one_can_deactivate_the_super_admin(client, users_store):
    super_admin = users_store.get_by_email(SUPER_ADMIN_EMAIL)
    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    resp = client.post(f"/auth/users/{super_admin['id']}/deactivate", headers=_auth(admin_token))
    assert resp.status_code == 403

    # Even the Super Admin acting on its own account is blocked (also
    # covered by the self-deactivation rule below, belt-and-braces here).
    super_token = _token(client, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    resp2 = client.post(f"/auth/users/{super_admin['id']}/deactivate", headers=_auth(super_token))
    assert resp2.status_code == 403


def test_admin_can_deactivate_authority_and_field_officer(client, make_user):
    authority = make_user(role="authority")
    field = make_user(role="field_officer")
    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    resp1 = client.post(f"/auth/users/{authority['id']}/deactivate", headers=_auth(admin_token))
    assert resp1.status_code == 200
    resp2 = client.post(f"/auth/users/{field['id']}/deactivate", headers=_auth(admin_token))
    assert resp2.status_code == 200


def test_authority_can_deactivate_field_officer_but_not_admin_or_authority(client, make_user):
    field = make_user(role="field_officer")
    other_authority = make_user(role="authority")
    authority_token = _token(client, AUTHORITY_EMAIL, AUTHORITY_PASSWORD)

    resp = client.post(f"/auth/users/{field['id']}/deactivate", headers=_auth(authority_token))
    assert resp.status_code == 200

    resp2 = client.post(f"/auth/users/{other_authority['id']}/deactivate", headers=_auth(authority_token))
    assert resp2.status_code == 403

    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    admin_row = client.get("/auth/me", headers=_auth(admin_token)).json()
    resp3 = client.post(f"/auth/users/{admin_row['id']}/deactivate", headers=_auth(authority_token))
    assert resp3.status_code == 403


def test_field_officer_cannot_deactivate_anyone(client, make_user):
    other_field = make_user(role="field_officer")
    field_token = _token(client, FIELD_EMAIL, FIELD_PASSWORD)
    resp = client.post(f"/auth/users/{other_field['id']}/deactivate", headers=_auth(field_token))
    assert resp.status_code == 403


def test_cannot_deactivate_own_account(client):
    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    me = client.get("/auth/me", headers=_auth(admin_token)).json()
    resp = client.post(f"/auth/users/{me['id']}/deactivate", headers=_auth(admin_token))
    assert resp.status_code == 403


def test_deactivate_nonexistent_account_404(client):
    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    resp = client.post(f"/auth/users/{uuid.uuid4()}/deactivate", headers=_auth(admin_token))
    assert resp.status_code == 404


def test_reactivate_account(client, make_user):
    field = make_user(role="field_officer", is_active=False)
    admin_token = _token(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    blocked_login = client.post("/auth/login", json={"email": field["email"], "password": field["password"]})
    assert blocked_login.status_code == 403

    resp = client.post(f"/auth/users/{field['id']}/activate", headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True

    ok_login = client.post("/auth/login", json={"email": field["email"], "password": field["password"]})
    assert ok_login.status_code == 200
