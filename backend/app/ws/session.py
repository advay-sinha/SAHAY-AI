"""Session WebSocket.

    WSS /ws/session/{session_id}?token=<jwt>        (frozen contract)

Victim connections:
  * the token's session claim must match the path, or the socket is refused;
  * UP `chat.message` -> a text turn through services.intake.submit_turn;
  * UP `request_human` -> services.intake.request_human;
  * DOWN only the four victim-safe events (enforced by the hub).

Executive and supervisor connections subscribe to a case's session to watch it
live: transcript, assessment, alerts, recommendations, packet readiness. They
send nothing UP in this slice (officer messaging is deferred).

On connect every client receives the current session.status from the database,
so a reconnect resumes cleanly: the database, not the socket, holds the state.

The token in the URL is redacted from logs (app/core/log_redaction.py). This
module never logs a token, a URL, or message text.
"""

import json
from uuid import uuid4

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from ..core.db import session_factory
from ..core.errors import DomainError
from ..core.security import InvalidToken, decode_token
from ..services import intake
from ..services.events import publish
from .events import ROLE_VICTIM, ROLES
from .hub import Connection, hub

router = APIRouter(tags=["ws"])


async def _refuse(websocket: WebSocket) -> None:
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


@router.websocket("/ws/session/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str, token: str = Query(default="")) -> None:
    try:
        claims = decode_token(token)
    except InvalidToken:
        await _refuse(websocket)
        return
    role = claims.get("role")
    if role not in ROLES:
        await _refuse(websocket)
        return
    if role == ROLE_VICTIM and claims.get("sid") != session_id:
        await _refuse(websocket)  # a victim token reaches only its own session
        return

    async with session_factory()() as db:
        try:
            session = await intake.get_session_row(db, session_id)
            consent = await intake.consent_for(db, session_id)
            case = await intake.case_for_session(db, session_id)
        except DomainError:
            await _refuse(websocket)
            return
        snapshot = intake.status_payload(session, consent)
        case_id = case.id

    await websocket.accept()

    async def _send(frame: str) -> None:
        await websocket.send_text(frame)

    async def _close() -> None:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)

    conn = hub.subscribe(Connection(connection_id=str(uuid4()), session_id=session_id, role=role,
                                    send=_send, close=_close))
    hub.send_to(conn, "session.status", snapshot)

    try:
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                break
            text = raw.get("text")
            if text is None or role != ROLE_VICTIM:
                continue  # binary audio frames are deferred; staff send nothing up
            try:
                message = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(message, dict):
                continue
            kind = message.get("type")
            try:
                async with session_factory()() as db:
                    if kind == "chat.message":
                        out = await intake.submit_turn(db, session_id, str(message.get("text", "")),
                                                       message.get("lang"))
                    elif kind == "request_human":
                        out = await intake.request_human(db, session_id)
                    else:
                        continue
                    await db.commit()
                publish(session_id, case_id, out)
            except DomainError:
                # e.g. empty or over-long message, ended session. The victim's
                # screen is driven by session.status; resend the current one.
                async with session_factory()() as db:
                    s = await intake.get_session_row(db, session_id)
                    hub.send_to(conn, "session.status",
                                intake.status_payload(s, await intake.consent_for(db, session_id)))
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(conn)
