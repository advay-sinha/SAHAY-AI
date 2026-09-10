"""REST routes. Shapes are fixed by docs/contracts/CONTRACTS.md section 4."""

from fastapi import APIRouter

from . import auth, cases, sessions

router = APIRouter()
router.include_router(auth.router)
router.include_router(sessions.router)
router.include_router(cases.router)

__all__ = ["router"]
