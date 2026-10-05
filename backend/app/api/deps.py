from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_access_token
from app.core.supabase_users import UsersStore, get_users_store

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme), store: UsersStore = Depends(get_users_store)
) -> Optional[dict]:
    """Non-fatal auth: returns None if no/invalid token. Endpoints that
    require auth should check for None explicitly. This keeps the MVP
    demonstrable (e.g. GET endpoints) without forcing a full auth flow
    everywhere, while POST/mutation endpoints that matter still enforce it.

    User lookup is now Supabase (the `users` table), not the Excel `users`
    sheet — see app/core/supabase_users.py. Building the store here does
    not itself make a network call (it just wraps an httpx.Client), so an
    anonymous request (no token) still returns None immediately below
    without ever touching Supabase."""
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user = store.get_by_email(payload.get("sub"))
    if not user or not user.get("is_active"):
        # A deactivated account must lose access immediately, not just be
        # blocked from a future login — JWTs are stateless, so without this
        # check a still-valid token issued before deactivation would keep
        # working on every other endpoint until it naturally expired.
        return None
    return user


def require_user(user: Optional[dict] = Depends(get_current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user
