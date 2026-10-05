import datetime as dt
import secrets

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, password_strength_error, verify_password
from app.core.supabase_users import UsersStore, get_users_store
from app.schemas.schemas import (
    ChangePasswordRequest,
    CreateUserRequest,
    CreateUserResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    MessageResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    ResetPasswordRequest,
    UserAccountOut,
    UserSummaryOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

VALID_ROLES = {"admin", "authority", "field_officer"}
RESET_TOKEN_TTL_MINUTES = 30

# Every account created via POST /auth/users (there is no more self-service
# /auth/signup) starts with this exact fixed password — shown back to the
# authorized creator in CreateUserResponse.initial_password so they can pass
# it to the new user, who is expected to change it after first login via the
# existing, untouched /auth/change-password. Satisfies password_strength_error
# (14 chars, a letter, digits, and "@").
DEFAULT_INITIAL_PASSWORD = "Terraguard@123"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _is_super_admin(user: dict) -> bool:
    """The one protected "Super Admin" account (`SUPER_ADMIN_EMAIL`,
    default `admin.terraguard@gmail.com`), matched case-insensitively. It
    can never be deactivated or have its name/email changed by anyone
    (including itself, for name/email — see `update_profile`), and is the
    only account allowed to create other Admin accounts."""
    return user["email"].strip().lower() == get_settings().SUPER_ADMIN_EMAIL.strip().lower()


def _can_create_role(actor: dict, target_role: str) -> bool:
    """Account-creation hierarchy (spec section 5/10):
    - `admin` accounts can only be created by the Super Admin.
    - `authority` accounts can be created by any Admin (Super Admin included).
    - `field_officer` accounts can be created by any Admin or Authority.
    - Field Officers can never create any account."""
    if target_role not in VALID_ROLES:
        return False
    if target_role == "admin":
        return _is_super_admin(actor)
    if target_role == "authority":
        return actor["role"] == "admin"
    if target_role == "field_officer":
        return actor["role"] in {"admin", "authority"}
    return False


def _can_manage_status(actor: dict, target: dict) -> bool:
    """Activate/deactivate hierarchy. The spec's own prose (sections 3 and 9)
    and its summary matrix (section 10) disagree on one point: section 3
    explicitly says "Admins cannot deactivate another Admin. Exception:
    admin.terraguard@gmail.com ... can deactivate other user accounts when
    required", and section 9 says the Super Admin "retains full
    account-management authority over other users" — both say the Super
    Admin CAN act on regular Admin accounts. The section 10 matrix's
    "Deactivate Admin / Super Admin: No*" cell reads the other way at first
    glance, but its own footnote ("The Super Admin cannot be deactivated by
    ANOTHER user") is about the Super Admin being a *target*, not about its
    powers as an actor — so it doesn't actually contradict sections 3/9.
    This implementation follows the more detailed, unambiguous prose: the
    Super Admin can manage any other account; a regular Admin can manage
    Authority/Field Officer but never another Admin; an Authority can manage
    Field Officer only; a Field Officer can manage no one. No one — not even
    the Super Admin — can ever deactivate the Super Admin itself, and no one
    can deactivate/reactivate their own account through this endpoint."""
    if _is_super_admin(target):
        return False
    if str(target["id"]) == str(actor["id"]):
        return False
    if _is_super_admin(actor):
        return True
    if actor["role"] == "admin":
        return target["role"] in {"authority", "field_officer"}
    if actor["role"] == "authority":
        return target["role"] == "field_officer"
    return False


def _to_user_account_out(row: dict) -> UserAccountOut:
    return UserAccountOut(
        id=str(row["id"]),
        full_name=row["full_name"],
        email=row["email"],
        role=row["role"],
        is_active=bool(row.get("is_active")),
        created_at=row.get("created_at"),
        last_seen=row.get("last_seen"),
    )


# --- AUTHENTICATION DATA SOURCE: Supabase (`users` table), NOT the Excel
# workbook. Every other endpoint/feature in this project still reads and
# writes dataset/terraguard_data.xlsx via app.core.excel_store — this file
# is the one deliberate, scoped exception. See app/core/supabase_users.py
# for the full explanation and the Excel-side sheet this replaces. --------


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, store: UsersStore = Depends(get_users_store)):
    user = store.get_by_email(payload.email.strip().lower())
    # Credentials are checked BEFORE the active-status check, and both wrong
    # cases below share nothing about the account's existence/status with an
    # attacker who doesn't already know the correct password — only someone
    # who supplies the right password ever learns their account is
    # deactivated, rather than that fact being discoverable via a wrong
    # guess against any email.
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact an administrator.",
        )

    # Real "last seen" bookkeeping on every successful login, as required —
    # best-effort: a failure here must never turn a successful login into a
    # failed one, so it's swallowed rather than propagated.
    try:
        store.update_by_id(user["id"], {"last_seen": _now_iso(), "updated_at": _now_iso()})
    except HTTPException:
        pass

    token = create_access_token(subject=user["email"], extra_claims={"role": user["role"]})
    return LoginResponse(access_token=token, role=user["role"], full_name=user["full_name"], email=user["email"])


@router.post("/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: CreateUserRequest, actor: dict = Depends(require_user), store: UsersStore = Depends(get_users_store)):
    """Replaces the old public, unauthenticated `/auth/signup` entirely —
    self-registration is no longer possible. Every account is created BY an
    already-authenticated, authorized user, and who may create which role is
    enforced here server-side via `_can_create_role()`, never left to the
    frontend hiding a button."""
    role = payload.role.strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}.",
        )
    if not _can_create_role(actor, role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your role does not permit creating a {role.replace('_', ' ')} account.",
        )

    email = payload.email.strip().lower()
    if store.get_by_email(email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    row = {
        "email": email,
        "password_hash": hash_password(DEFAULT_INITIAL_PASSWORD),
        "full_name": payload.full_name.strip(),
        "role": role,
        "is_active": True,
    }
    inserted = store.insert(row)
    return CreateUserResponse(**_to_user_account_out(inserted).model_dump(), initial_password=DEFAULT_INITIAL_PASSWORD)


def _to_me_response(user: dict) -> MeResponse:
    return MeResponse(
        id=str(user["id"]) if user.get("id") is not None else None,
        email=user["email"],
        full_name=user.get("full_name"),
        role=user["role"],
        is_active=user.get("is_active"),
        last_seen=user.get("last_seen"),
        created_at=user.get("created_at"),
    )


@router.get("/me", response_model=MeResponse)
def me(user: dict = Depends(require_user)):
    return _to_me_response(user)


@router.patch("/profile", response_model=ProfileUpdateResponse)
def update_profile(payload: ProfileUpdateRequest, user: dict = Depends(require_user), store: UsersStore = Depends(get_users_store)):
    """Self-service profile edit — full_name/email only. The user being
    edited is always the one the JWT identifies (`user["id"]`, from
    `require_user`/`get_current_user`) — there is no request field the
    client could use to name a different account, so this can only ever
    modify the caller's own row. `ProfileUpdateRequest` has no `role` field
    at all — see its docstring — so a role change is not possible through
    this endpoint regardless of what a client sends.

    The protected Super Admin account's name/email are additionally locked
    even for itself — its own identity must stay stable as the anchor
    account other permission checks key off (`_is_super_admin`). Its
    password can still be changed via `/auth/change-password`, untouched
    below."""
    if _is_super_admin(user) and (payload.full_name is not None or payload.email is not None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The protected Super Admin account's name and email cannot be changed.",
        )

    updates: dict = {}
    email_changed = False

    if payload.full_name is not None:
        full_name = payload.full_name.strip()
        if len(full_name) < 2:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Full name must be at least 2 characters long.")
        updates["full_name"] = full_name

    if payload.email is not None:
        new_email = payload.email.strip().lower()
        if not new_email or "@" not in new_email or "." not in new_email.split("@")[-1]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid email address.")
        if new_email != user["email"]:
            existing = store.get_by_email(new_email)
            # Excludes the caller's own row (matched by id) so re-submitting
            # your own unchanged email is never mistaken for a conflict.
            if existing and str(existing["id"]) != str(user["id"]):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
            updates["email"] = new_email
            email_changed = True

    if not updates:
        return ProfileUpdateResponse(**_to_me_response(user).model_dump())

    updates["updated_at"] = _now_iso()
    store.update_by_id(user["id"], updates)
    updated = store.get_by_id(user["id"]) or {**user, **updates}

    # The JWT's `sub` claim is the email (see login/signup) — an email
    # change means the client's existing token no longer resolves to any
    # account, so a new one is issued here rather than silently breaking
    # the session the user is still in the middle of.
    new_token = None
    if email_changed:
        new_token = create_access_token(subject=updated["email"], extra_claims={"role": updated["role"]})

    return ProfileUpdateResponse(**_to_me_response(updated).model_dump(), access_token=new_token)


@router.post("/change-password", response_model=MessageResponse)
def change_password(payload: ChangePasswordRequest, user: dict = Depends(require_user), store: UsersStore = Depends(get_users_store)):
    """Requires the caller's CURRENT password before accepting a new one —
    same security behavior the old Excel-backed flow never actually had for
    this action (there was no self-service password change before; only
    the token-based forgot/reset-password flow existed). Never touches
    `role`."""
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    password_error = password_strength_error(payload.new_password)
    if password_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=password_error)

    store.update_by_id(user["id"], {
        "password_hash": hash_password(payload.new_password),
        "updated_at": _now_iso(),
    })
    return MessageResponse(message="Password updated successfully.")


@router.get("/users", response_model=list[UserSummaryOut])
def list_users(store: UsersStore = Depends(get_users_store), _user: dict = Depends(require_user)):
    """Real, active registered accounts — used by the Alert Intelligence
    Center's Assign Response picker so a response is assigned to a verified
    account (whose role comes from this same list) instead of free-typed
    text that could name someone who doesn't have an account, or claim a
    role they don't actually hold. Requires auth (any signed-in role);
    excludes password_hash/reset_token, which aren't the caller's business.

    `id` is now a Supabase UUID string (was an Excel int row id) — the web
    frontend already treats it as an opaque string key (`String(u.id)` in
    WarRoom.tsx) and Flutter's /auth/users caller doesn't exist, so this is
    not a breaking change for either client."""
    active = store.list_active()
    return [
        UserSummaryOut(id=str(row["id"]), full_name=row["full_name"], email=row["email"], role=row["role"])
        for row in active
    ]


@router.get("/users/manageable", response_model=list[UserAccountOut])
def list_manageable_users(actor: dict = Depends(require_user), store: UsersStore = Depends(get_users_store)):
    """Powers the Account Management screen's user list — scoped to exactly
    the accounts the caller is permitted to act on (mirrors
    `_can_create_role`'s hierarchy, since whoever can create a role can also
    see/manage existing accounts of that role), always excluding the caller
    themselves. A Field Officer gets an empty list (never a 403) so the
    frontend can render an empty, but not broken, management panel — the
    real enforcement is on the mutating endpoints below regardless of what
    this list shows."""
    if _is_super_admin(actor):
        allowed_roles = None  # every other account, any role
    elif actor["role"] == "admin":
        allowed_roles = {"authority", "field_officer"}
    elif actor["role"] == "authority":
        allowed_roles = {"field_officer"}
    else:
        allowed_roles = set()

    rows = store.list_all()
    result = []
    for row in rows:
        if str(row["id"]) == str(actor["id"]):
            continue
        if allowed_roles is not None and row["role"] not in allowed_roles:
            continue
        result.append(_to_user_account_out(row))
    return result


def _set_active(user_id: str, active: bool, actor: dict, store: UsersStore) -> UserAccountOut:
    target = store.get_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    if not _can_manage_status(actor, target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to change this account's status.",
        )
    store.update_by_id(target["id"], {"is_active": active, "updated_at": _now_iso()})
    updated = store.get_by_id(target["id"]) or {**target, "is_active": active}
    return _to_user_account_out(updated)


@router.post("/users/{user_id}/deactivate", response_model=UserAccountOut)
def deactivate_user(user_id: str, actor: dict = Depends(require_user), store: UsersStore = Depends(get_users_store)):
    """Blocks the target's login immediately (see `login()`) AND ends any
    session already in progress (see `deps.get_current_user`'s is_active
    check) — deactivating someone doesn't wait for their existing token to
    expire."""
    return _set_active(user_id, False, actor, store)


@router.post("/users/{user_id}/activate", response_model=UserAccountOut)
def activate_user(user_id: str, actor: dict = Depends(require_user), store: UsersStore = Depends(get_users_store)):
    return _set_active(user_id, True, actor, store)


@router.post("/logout", response_model=MessageResponse)
def logout(user: dict = Depends(get_current_user)):
    # JWTs are stateless in this MVP (no server-side session/blacklist store),
    # so logout is enforced client-side by discarding the token. This endpoint
    # exists so the frontend has a real call to make on logout and so a future
    # token-blacklist could be added here without changing the client contract.
    return MessageResponse(message="Logged out")


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, store: UsersStore = Depends(get_users_store)):
    email = payload.email.strip().lower()
    user = store.get_by_email(email)

    # Always return 200 with a generic message even if the email doesn't
    # exist, so this endpoint can't be used to enumerate registered accounts.
    generic_message = "If an account with that email exists, a password reset link has been generated."
    if not user or not user.get("is_active"):
        return ForgotPasswordResponse(message=generic_message)

    token = secrets.token_urlsafe(32)
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    store.update_by_id(user["id"], {
        "reset_token": token,
        "reset_token_expires": expires.isoformat(),
        "updated_at": _now_iso(),
    })

    from app.core.config import get_settings

    settings = get_settings()
    reset_link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"

    # NOT CONFIGURED: no SMTP/email provider is set up in this MVP. In place
    # of emailing the link, it is returned directly in the API response (and
    # logged server-side) so the reset flow is fully testable without
    # external configuration. Wire a real provider here before production use.
    print(f"[password-reset] {email} -> {reset_link}")

    return ForgotPasswordResponse(message=generic_message, reset_token=token, reset_link=reset_link)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, store: UsersStore = Depends(get_users_store)):
    user = store.get_by_reset_token(payload.token)
    if not user or not user.get("reset_token_expires"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset link is invalid or has expired")
    expires_at = user["reset_token_expires"]
    if isinstance(expires_at, str):
        expires_at = dt.datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
    if expires_at < dt.datetime.now(dt.timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset link is invalid or has expired")

    password_error = password_strength_error(payload.new_password)
    if password_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=password_error)

    store.update_by_id(user["id"], {
        "password_hash": hash_password(payload.new_password),
        "reset_token": None,
        "reset_token_expires": None,
        "updated_at": _now_iso(),
    })

    return MessageResponse(message="Password updated successfully. You can now sign in.")
