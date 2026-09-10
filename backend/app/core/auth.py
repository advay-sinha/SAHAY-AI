"""REST authentication and role-based access control.

Backend RBAC is authoritative. The console hides navigation by role, but that
is convenience only: every protected route checks the token here.

The token is read from the `Authorization: Bearer` header and nowhere else.
A `?token=` query parameter on a REST route is ignored, so a token cannot be
smuggled in through a URL that would end up in history or logs.

Status codes:
  401  no token, malformed token, bad signature, expired, missing claims
       (with `WWW-Authenticate: Bearer`)
  403  a valid token whose role may not use this route
"""

from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import Depends, Header, HTTPException, status

from ..ws.events import ROLE_EXECUTIVE, ROLE_SUPERVISOR, ROLE_VICTIM
from .security import InvalidToken, decode_token

#: Roles that may use the executive console REST surface.
CONSOLE_ROLES = (ROLE_EXECUTIVE, ROLE_SUPERVISOR)
#: Roles that may read the victim-safe timeline (the victim app, and staff).
TIMELINE_ROLES = (ROLE_VICTIM, ROLE_EXECUTIVE, ROLE_SUPERVISOR)

#: Deliberately uninformative. The same text for every authentication failure,
#: so a client cannot tell an expired token from a forged one.
_UNAUTHENTICATED = "Not authenticated"
_FORBIDDEN = "Not permitted for this role"


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    session_id: Optional[str] = None


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_UNAUTHENTICATED,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_principal(authorization: Optional[str] = Header(default=None)) -> Principal:
    """Resolve the caller from `Authorization: Bearer <jwt>`. Fails closed."""
    if not authorization:
        raise _unauthenticated()
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        raise _unauthenticated()
    try:
        claims = decode_token(credentials.strip())
    except InvalidToken:
        raise _unauthenticated() from None
    return Principal(subject=claims["sub"], role=claims["role"], session_id=claims.get("sid"))


def require_roles(*roles: str) -> Callable[..., Principal]:
    """Dependency factory: allow only these roles; 403 for any other valid role."""
    allowed = frozenset(roles)

    def _dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN)
        return principal

    return _dependency


require_console = require_roles(*CONSOLE_ROLES)
require_supervisor = require_roles(ROLE_SUPERVISOR)
require_timeline_reader = require_roles(*TIMELINE_ROLES)
