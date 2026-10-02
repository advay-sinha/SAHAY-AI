"""Session lifecycle.

Responses here are victim-facing. They use VictimSafeModel schemas, which
forbid unknown fields, so an assessment field cannot be added by accident.

Text turns and human requests arrive over the session WebSocket as the
contract's `chat.message` and `request_human` events (CONTRACTS.md section 1);
they are handled in app/ws/session.py through the same services used here.
Voice turns arrive as a whole-utterance upload (PC-11) and join the same path.
"""

import asyncio
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.asr import ASRRejected, ASRUnavailable, get_provider as get_asr
from ..adapters.tts import SynthesisUnavailable, get_provider as get_tts
from ..core.auth import Principal, ensure_session_access, require_any
from ..core.config import get_settings
from ..core.db import get_session
from ..core.enums import AUDIO_CHANNELS, AUDIO_MAX_BYTES, AUDIO_MEDIA_TYPES
from ..core.errors import (BadRequest, Conflict, Forbidden, NotFound, PayloadTooLarge, ServiceUnavailable,
                           TooManyRequests, UnsupportedMediaType)
from ..core.security import create_token
from ..schemas.contracts import (AudioUploadResponse, CreateSessionRequest, CreateSessionResponse,
                                 EndSessionResponse)
from ..services import audit, intake, latency
from ..services.consent import CONSENT_GRANTED, session_capabilities
from ..services.events import publish
from ..services.rate_limit import session_limiter
from ..ws.events import ROLE_VICTIM

router = APIRouter(prefix="/sessions", tags=["sessions"])

AI_DISCLOSURE = intake.AI_DISCLOSURE


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest, request: Request, db: AsyncSession = Depends(get_session)
) -> CreateSessionResponse:
    client = request.client.host if request.client else "unknown"
    if not session_limiter.allow(client, get_settings().SESSION_RATE_LIMIT_PER_HOUR):
        raise TooManyRequests("too many sessions; try again later")
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


@router.post("/{session_id}/audio", response_model=AudioUploadResponse)
async def upload_audio(
    session_id: str,
    request: Request,
    lang: Optional[str] = Query(default=None),
    principal: Principal = Depends(require_any),
    db: AsyncSession = Depends(get_session),
) -> AudioUploadResponse:
    """Whole-utterance voice turn (PC-11).

    The audio is transcribed through the ASR adapter. A transcript then takes exactly the
    same path as a typed ``chat.message`` (intake.submit_turn): crisis pre-check first, then
    the dialogue policy. The response carries only ``turn_id`` and ``status``; the ASR
    confidence and audio measurements stay on the server for the console.
    """
    ensure_session_access(principal, session_id)
    if principal.role != ROLE_VICTIM:
        raise Forbidden("only the session's own victim token may upload audio")
    media = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if media not in AUDIO_MEDIA_TYPES:
        raise UnsupportedMediaType("send audio/wav, audio/mp4 or audio/aac")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > AUDIO_MAX_BYTES:
        raise PayloadTooLarge("audio is larger than 5 MB")

    session = await intake.get_session_row(db, session_id)
    if session.ended_at is not None:
        raise Conflict("session has ended")
    if session.channel not in AUDIO_CHANNELS:
        raise Conflict("this session is not a voice session")
    if await intake.consent_for(db, session_id) != CONSENT_GRANTED:
        raise Conflict("consent has not been granted")
    lang = lang or session.lang
    if lang not in ("hi", "en"):
        raise BadRequest("lang must be hi or en")

    audio = await request.body()
    received = time.perf_counter()
    if not audio:
        raise BadRequest("the request carried no audio")
    if len(audio) > AUDIO_MAX_BYTES:
        raise PayloadTooLarge("audio is larger than 5 MB")

    try:
        t_asr = time.perf_counter()
        result = await get_asr(get_settings()).transcribe(audio, media, lang)
        asr_request_ms = round(1000 * (time.perf_counter() - t_asr), 3)
    except ASRRejected as exc:
        if exc.status == 413:
            raise PayloadTooLarge("audio is longer than 60 seconds or larger than 5 MB") from None
        if exc.status == 415:
            raise UnsupportedMediaType("send audio/wav, audio/mp4 or audio/aac") from None
        raise BadRequest("the audio request was refused") from None
    except ASRUnavailable:
        raise ServiceUnavailable("speech recognition is unavailable; please use Chat") from None

    case = await intake.case_for_session(db, session_id)
    text = (result.get("text") or "").strip() if result["status"] == "transcribed" else ""
    if not text:
        outcome = "no_speech" if result["status"] in ("transcribed", "no_speech") else "audio_unreadable"
        await audit.record(db, f"asr.{outcome}", case_id=case.id,
                           detail={"duration_s": result.get("duration_s"), "speech_s": result.get("speech_s")})
        await db.commit()
        return AudioUploadResponse(turn_id=None, status=outcome)

    out = await intake.submit_turn(db, session_id, text, lang, asr=result)
    await audit.record(db, "asr.accepted", case_id=case.id, detail={
        "asr_confidence": result.get("asr_confidence"), "poor_audio": result.get("poor_audio"),
        "low_asr_confidence": result.get("low_asr_confidence"), "timings_ms": result.get("timings_ms")})
    turn_id = next((p["turn_id"] for kind, p in out.events
                    if kind == "transcript.line" and p.get("speaker") == "victim"), None)
    latency.record(db, session_id, turn_id, {"asr_request": asr_request_ms,
                                             "request_total": round(1000 * (time.perf_counter() - received), 3)})
    await db.commit()
    publish(session_id, case.id, out)
    return AudioUploadResponse(turn_id=turn_id, status="accepted")


FIXED_SCRIPT_STATES = ("S0", "S9", "SX", "SH")
WAV_HEADERS = {"Cache-Control": "no-store"}


@router.get("/{session_id}/turns/{turn_id}/audio", response_class=Response,
            responses={200: {"content": {"audio/wav": {}}}, 404: {"description": "no approved audio"}})
async def turn_audio(
    session_id: str,
    turn_id: str,
    principal: Principal = Depends(require_any),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Audio for one assistant turn (PC-12). 404 whenever no approved audio exists; the client
    then shows the text it already has.

    Fixed scripts (S0, S9, SX, SH) come only from approved human recordings (``ml.tts.presynth``)
    and are never synthesised. Other assistant turns exist only for validated or language-approved
    text, and are spoken with the configured offline voice once, then cached.
    """
    from ml.tts import presynth

    from ..models import Turn

    ensure_session_access(principal, session_id)
    if principal.role != ROLE_VICTIM:
        raise Forbidden("only the session's own victim token may fetch turn audio")
    turn = await db.get(Turn, turn_id)
    if turn is None or turn.session_id != session_id or turn.speaker != "assistant" or not turn.text:
        raise NotFound("no audio for this turn")
    settings = get_settings()
    if turn.state in FIXED_SCRIPT_STATES:
        path = presynth.servable(turn.state, turn.lang, Path(settings.FIXED_AUDIO_ROOT))
        if path is None:
            raise NotFound("no approved recording for this script")
        return Response(content=path.read_bytes(), media_type="audio/wav", headers=WAV_HEADERS)

    cache = Path(settings.AUDIO_STORAGE_PATH) / "tts" / f"{turn.id}.wav"
    if cache.is_file():
        return Response(content=cache.read_bytes(), media_type="audio/wav", headers=WAV_HEADERS)
    started = time.perf_counter()
    try:
        audio = await asyncio.to_thread(get_tts(settings).synthesize, turn.text, turn.lang)
    except SynthesisUnavailable:
        audio = b""
    if not audio:
        raise NotFound("no voice available for this turn")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(audio)
    latency.record(db, session_id, turn.id, {"tts_synthesis": round(1000 * (time.perf_counter() - started), 3)})
    await db.commit()
    return Response(content=audio, media_type="audio/wav", headers=WAV_HEADERS)


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
