"""Authenticated session WebSocket for the controlled text MVP.

Authentication is the exact first text frame and no domain data is sent before
``auth.ok``. This module never logs URLs, tokens, auth frames, or submitted text.
"""

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..core.db import session_factory
from ..core.errors import Conflict, DomainError
from ..core.security import InvalidToken, decode_token
from ..schemas.contracts import ChatMessage, RequestHuman
from ..services import intake
from ..services.events import publish
from .events import ROLE_VICTIM, ROLES
from .hub import Connection, hub

router = APIRouter(tags=["ws"])

AUTH_TIMEOUT_SECONDS = 5
CLOSE_PROTOCOL = 4400
CLOSE_AUTH = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_INTERNAL = 1011


async def _close(websocket: WebSocket, code: int) -> None:
    await websocket.close(code=code, reason="")


def _json_object(text: str):
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


async def _authenticate(websocket: WebSocket, session_id: str):
    try:
        raw = await asyncio.wait_for(websocket.receive(), timeout=AUTH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await _close(websocket, CLOSE_AUTH)
        return None
    if raw.get("type") == "websocket.disconnect":
        return None
    text = raw.get("text")
    if text is None:
        await _close(websocket, CLOSE_PROTOCOL)
        return None
    try:
        message = _json_object(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        await _close(websocket, CLOSE_PROTOCOL)
        return None
    if message.get("type") != "auth":
        await _close(websocket, CLOSE_PROTOCOL)
        return None
    if set(message) != {"type", "token"}:
        # A missing token is an authentication failure; every other shape error
        # is a protocol failure.
        await _close(websocket, CLOSE_AUTH if "token" not in message else CLOSE_PROTOCOL)
        return None
    token = message.get("token")
    if not isinstance(token, str) or not token:
        await _close(websocket, CLOSE_AUTH)
        return None
    try:
        claims = decode_token(token)
    except InvalidToken:
        await _close(websocket, CLOSE_AUTH)
        return None
    role = claims.get("role")
    if role not in ROLES:
        await _close(websocket, CLOSE_AUTH)
        return None
    if role == ROLE_VICTIM and claims.get("sid") != session_id:
        await _close(websocket, CLOSE_FORBIDDEN)
        return None

    async with session_factory()() as db:
        try:
            session = await intake.get_session_row(db, session_id)
            consent = await intake.consent_for(db, session_id)
            case = await intake.case_for_session(db, session_id)
        except DomainError:
            await _close(websocket, CLOSE_FORBIDDEN)
            return None
    return token, role, session, consent, case.id


def _chat_rejection(message: ChatMessage, error: str):
    return {"type": "chat.ack", "client_message_id": message.client_message_id,
            "status": "rejected", "error": error}


def _human_rejection(message: RequestHuman, error: str):
    return {"type": "human_request.ack", "request_id": message.request_id,
            "status": "rejected", "error": error}


@router.websocket("/ws/session/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    if websocket.url.query:
        await _close(websocket, CLOSE_PROTOCOL)
        return

    authenticated = await _authenticate(websocket, session_id)
    if authenticated is None:
        return
    token, role, session, consent, case_id = authenticated

    await websocket.send_json({"type": "auth.ok", "session_id": session_id, "role": role})

    async def _send(frame: str) -> None:
        await websocket.send_text(frame)

    async def _drop_slow() -> None:
        await _close(websocket, 1013)

    conn = hub.subscribe(Connection(connection_id=str(uuid4()), session_id=session_id, role=role,
                                    send=_send, close=_drop_slow))
    hub.send_to(conn, "session.status", intake.status_payload(session, consent))

    try:
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                break
            try:
                decode_token(token)
            except InvalidToken:
                await _close(websocket, CLOSE_AUTH)
                break
            text = raw.get("text")
            if text is None:
                await _close(websocket, CLOSE_PROTOCOL)
                break
            try:
                message = _json_object(text)
            except (json.JSONDecodeError, TypeError, ValueError):
                await _close(websocket, CLOSE_PROTOCOL)
                break
            kind = message.get("type")
            if kind not in ("chat.message", "request_human"):
                await _close(websocket, CLOSE_PROTOCOL)
                break
            if role != ROLE_VICTIM:
                await _close(websocket, CLOSE_FORBIDDEN)
                break

            if kind == "chat.message":
                try:
                    body = ChatMessage.model_validate(message)
                except ValidationError:
                    await _close(websocket, CLOSE_PROTOCOL)
                    break
                try:
                    async with session_factory()() as db:
                        out = await intake.submit_turn(
                            db, session_id, body.text, body.lang,
                            client_message_id=body.client_message_id,
                        )
                        await db.commit()
                except Conflict as exc:
                    error = "session_ended" if exc.message == "session has ended" else (
                        "id_conflict" if exc.message == "client message id conflict" else "not_permitted"
                    )
                    await websocket.send_json(_chat_rejection(body, error))
                    continue
                except Exception:
                    await _close(websocket, CLOSE_INTERNAL)
                    break
                await websocket.send_json({
                    "type": "chat.ack", "client_message_id": body.client_message_id,
                    "status": out.idempotency_status, "turn_id": out.persisted_id,
                })
                if out.idempotency_status == "accepted":
                    publish(session_id, case_id, out)
                continue

            try:
                body = RequestHuman.model_validate(message)
            except ValidationError:
                await _close(websocket, CLOSE_PROTOCOL)
                break
            try:
                async with session_factory()() as db:
                    out = await intake.request_human(db, session_id, body.request_id)
                    await db.commit()
            except Conflict as exc:
                error = "session_ended" if exc.message == "session has ended" else "not_permitted"
                await websocket.send_json(_human_rejection(body, error))
                continue
            except Exception:
                await _close(websocket, CLOSE_INTERNAL)
                break
            await websocket.send_json({
                "type": "human_request.ack", "request_id": body.request_id,
                "status": out.idempotency_status,
            })
            if out.idempotency_status == "accepted":
                publish(session_id, case_id, out)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(conn)
