"""Session lifecycle.

Responses here are victim-facing. They use VictimSafeModel schemas, which
forbid unknown fields, so an assessment field cannot be added by accident.

Text turns and human requests arrive over the session WebSocket as the
contract's `chat.message` and `request_human` events (CONTRACTS.md section 1);
they are handled in app/ws/session.py through the same services used here.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import Principal, ensure_session_access, require_any
from ..core.db import get_session
from ..core.security import create_token
from ..schemas.contracts import CreateSessionRequest, CreateSessionResponse, EndSessionResponse
from ..services import intake
from ..services.consent import session_capabilities
from ..services.events import publish
from ..ws.events import ROLE_VICTIM

router = APIRouter(prefix="/sessions", tags=["sessions"])

AI_DISCLOSURE = intake.AI_DISCLOSURE


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest, db: AsyncSession = Depends(get_session)
) -> CreateSessionResponse:
    session, case, out = await intake.create_session(db, body.channel, body.consent, body.lang)
    await db.commit()
    publish(session.id, case.id, out)

    token = create_token(f"victim:{session.id}", ROLE_VICTIM, session_id=session.id)
    caps = session_capabilities(body.consent)
    return CreateSessionResponse(
        session_id=session.id,
        case_id=case.id,
        reference_no=case.reference,
        session_token=token,
        ws_url=f"/ws/session/{session.id}",
        consent=body.consent,
        lang=body.lang,
        ai_disclosure=AI_DISCLOSURE,
        human_request_available=caps["human_request_available"],
    )


@router.post("/{session_id}/audio")
async def upload_audio(session_id: str):
    """Whole-utterance audio fallback. Audio is deferred in the text-first slice."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "audio intake is deferred")


@router.post("/{session_id}/end", response_model=EndSessionResponse)
async def end_session(
    session_id: str,
    principal: Principal = Depends(require_any),
    db: AsyncSession = Depends(get_session),
) -> EndSessionResponse:
    ensure_session_access(principal, session_id)
    case, out = await intake.end_session(db, session_id)
    await db.commit()
    publish(session_id, case.id, out)
    return EndSessionResponse(case_id=case.id, reference_no=case.reference)
