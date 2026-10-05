def test_login_success(client):
    resp = client.post("/auth/login", json={"email": "admin@terraguard.demo", "password": "Admin@123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["role"] == "admin"


def test_login_updates_last_seen(client, users_store):
    # Authentication is now Supabase-backed (see app/core/supabase_users.py)
    # — `users_store` is the same in-memory fake the app's dependency is
    # overridden with (see conftest.py), so we can assert on the real state
    # a login call actually left behind, not just its HTTP response.
    before = users_store.get_by_email("admin@terraguard.demo")

    resp = client.post("/auth/login", json={"email": "admin@terraguard.demo", "password": "Admin@123"})
    assert resp.status_code == 200

    after = users_store.get_by_email("admin@terraguard.demo")
    assert after["last_seen"] is not None
    assert after["last_seen"] != before["last_seen"]
    assert after["updated_at"] != before["updated_at"]


def test_login_wrong_password(client):
    resp = client.post("/auth/login", json={"email": "admin@terraguard.demo", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post("/auth/login", json={"email": "nobody@nowhere.test", "password": "x"})
    assert resp.status_code == 401


def _login_token(client):
    resp = client.post("/auth/login", json={"email": "admin@terraguard.demo", "password": "Admin@123"})
    return resp.json()["access_token"]


def test_list_users_requires_auth(client):
    resp = client.get("/auth/users")
    assert resp.status_code == 401


def test_list_users_returns_real_accounts_with_roles(client):
    token = _login_token(client)
    resp = client.get("/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    for entry in body:
        assert set(entry.keys()) == {"id", "full_name", "email", "role"}
        assert entry["role"] in {"admin", "authority", "field_officer"}
    # The seeded admin account must be present with its real role, not a
    # free-typed/guessed one.
    admin_entries = [e for e in body if e["email"] == "admin@terraguard.demo"]
    assert admin_entries and admin_entries[0]["role"] == "admin"


def test_signup_endpoint_no_longer_exists(client):
    # Self-registration was removed entirely — accounts can only be created
    # by an authorized existing user via the new, authenticated
    # POST /auth/users (see test_account_management.py). A request to the
    # old path must not silently succeed or fall through to anything else.
    resp = client.post(
        "/auth/signup",
        json={"full_name": "Nope", "email": "should.not.exist@terraguard.demo", "password": "Str0ng!Pass1", "role": "field_officer"},
    )
    assert resp.status_code == 404


def test_login_blocks_deactivated_account_with_clear_message(client, make_user):
    user = make_user(role="field_officer", is_active=False)
    resp = client.post("/auth/login", json={"email": user["email"], "password": user["password"]})
    assert resp.status_code == 403
    assert "deactivated" in resp.json()["detail"].lower()


def test_login_wrong_password_on_deactivated_account_still_says_invalid_credentials(client, make_user):
    # A wrong-password attempt must never leak whether a given email even
    # has an account, active or not — only the RIGHT password on a
    # deactivated account reveals the deactivation-specific message above.
    user = make_user(role="field_officer", is_active=False)
    resp = client.post("/auth/login", json={"email": user["email"], "password": "TotallyWrong1!"})
    assert resp.status_code == 401
    assert "deactivated" not in resp.json()["detail"].lower()


def test_deactivated_users_existing_token_is_rejected_immediately(client, make_user, users_store):
    # A token issued while still active must stop working the moment the
    # account is deactivated — not just block future logins.
    user = make_user(role="field_officer", is_active=True)
    login_resp = client.post("/auth/login", json={"email": user["email"], "password": user["password"]})
    token = login_resp.json()["access_token"]

    me_before = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_before.status_code == 200

    users_store.update_by_id(user["id"], {"is_active": False})

    me_after = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_after.status_code == 401
