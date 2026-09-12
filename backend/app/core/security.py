"""Authentication primitives: password hashing and JWTs.

PyJWT for tokens, pwdlib[argon2] for password hashing (EXT-001, APPROVED 2026-09-10).

The role on the token is what the WebSocket fan-out and the REST RBAC trust. A
victim token can never be upgraded client-side, which is why the allowlist in
app/ws/events.py and the checks in app/core/auth.py are keyed on this value.

Tokens travel in the `Authorization: Bearer` header for REST. WebSockets carry
the token only in the exact first client frame (CONTRACTS.md section 1). No URL
ever carries a token.
"""

import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, Optional

import jwt
from pwdlib import PasswordHash

from ..ws.events import ROLES
from .config import get_settings

password_hash = PasswordHash.recommended()

#: Claims every token must carry. A token missing any of them is rejected.
REQUIRED_CLAIMS = ("sub", "role", "iat", "exp")


class InvalidToken(Exception):
    """Missing, malformed, expired, badly signed or role-less token."""


def hash_password(plain: str) -> str:
    return password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A real Argon2 hash of a random value nobody knows.

    Verified against when the username does not exist, so an unknown username
    costs the same Argon2 work as a wrong password. Without it, response time
    alone would reveal which usernames exist.
    """
    return hash_password(secrets.token_urlsafe(32))


def verify_password_constant(plain: str, hashed: Optional[str]) -> bool:
    """Verify, doing equivalent work whether or not a user was found."""
    if hashed is None:
        password_hash.verify(plain, _dummy_hash())
        return False
    return password_hash.verify(plain, hashed)


def create_token(subject: str, role: str, session_id: Optional[str] = None) -> str:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRY_MINUTES),
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Verify signature, expiry and required claims. Fails closed.

    The algorithm list is pinned to the configured one, so a token declaring
    `alg: none` or a different algorithm is rejected rather than trusted.
    """
    if not token or not isinstance(token, str):
        raise InvalidToken("missing token")
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": list(REQUIRED_CLAIMS)},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken(type(exc).__name__) from exc

    if claims.get("role") not in ROLES:
        raise InvalidToken("unknown role")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise InvalidToken("bad subject")
    return claims
