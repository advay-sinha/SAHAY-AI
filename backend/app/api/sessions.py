"""Session lifecycle.

Every response on this router is victim-facing. They use VictimSafeModel
schemas, which forbid unknown fields, so an assessment field cannot be added
here by accident.
"""

from fastapi import APIRouter, HTTPException, status

from ..schemas.contracts import CreateSessionRequest, CreateSessionResponse
from ..services.consent import session_capabilities

router = APIRouter(prefix="/sessions", tags=["sessions"])

#: Shown on the consent screen and visible thereafter. Root CLAUDE.md invariant 7.
AI_DISCLOSURE = (
    "You are speaking with an AI assistant. A human officer reviews everything "
    "you say. You can ask to speak to a person at any time."
)


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(body: CreateSessionRequest) -> CreateSessionResponse:
    # P1: persist the session and consent rows and issue a victim-scoped token.
    caps = session_capabilities(body.consent)
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        f"session creation lands in P1 (capabilities resolved: {caps})",
    )


@router.post("/{session_id}/audio")
async def upload_audio(session_id: str):
    """Whole-utterance fallback. Always available, per CONTRACTS.md section 1."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "audio upload lands in P1")


@router.post("/{session_id}/end")
async def end_session(session_id: str):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "session end lands in P1")
