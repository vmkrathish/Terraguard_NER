import datetime as dt
import re
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()
ALGORITHM = "HS256"

# Single source of truth for the password-complexity rule, shared by every
# schema that accepts a new password (signup, reset-password) so the rule
# can never drift between endpoints. The web and Flutter clients mirror this
# exact rule client-side for instant feedback, but this is the one place
# that's actually enforced — a request that bypasses/skips client-side
# validation still gets rejected here.
#
# Rule (revised): at least 8 characters, containing at least one letter (any
# case — uppercase and lowercase are NOT separately required), at least one
# number, and at least one special/symbol character. An earlier version of
# this rule required a separate uppercase AND lowercase letter; that split
# was removed at the user's explicit request.
PASSWORD_MIN_LENGTH = 8
_LETTER_RE = re.compile(r"[A-Za-z]")
_DIGIT_RE = re.compile(r"[0-9]")
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def password_strength_error(password: str) -> Optional[str]:
    """Returns a plain-language error string if `password` fails the
    complexity rule, or None if it passes. Kept as a plain function (rather
    than embedded directly in a Pydantic validator) so it can also be unit
    tested and reused by both SignupRequest and ResetPasswordRequest."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
    if not _LETTER_RE.search(password):
        return "Password must include at least one letter."
    if not _DIGIT_RE.search(password):
        return "Password must include at least one number."
    if not _SPECIAL_RE.search(password):
        return "Password must include at least one special character (e.g. !@#$%^&*)."
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, extra_claims: Optional[dict] = None) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
