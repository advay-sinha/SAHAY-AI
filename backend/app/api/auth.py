"""POST /auth/login. Executive and supervisor accounts only.

Contract: HANDOVER.md section 12.4, `POST /auth/login -> {token, role}`.
`display_name` is returned as well, additively, for the console header.

A victim never logs in; a victim session gets a scoped token from
POST /sessions with role=victim.

Username enumeration: an unknown username and a wrong password produce the
same status, the same body and — through verify_password_constant — the same
Argon2 work. Passwords and hashes are never logged or returned.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CONSOLE_ROLES
from ..core.db import get_session
from ..core.security import create_token, verify_password_constant
from ..models import User
from ..schemas.contracts import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = "Invalid username or password"


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: {"description": INVALID_CREDENTIALS}},
)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_session)) -> LoginResponse:
    user = (
        await db.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()

    # Always verify, even for an unknown username, so timing does not leak.
    ok = verify_password_constant(body.password, user.password_hash if user else None)

    if not ok or user is None or user.role not in CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return LoginResponse(
        token=create_token(user.id, user.role),
        role=user.role,
        display_name=user.display_name,
    )
