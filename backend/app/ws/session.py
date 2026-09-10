"""Session WebSocket.

    WSS /ws/session/{session_id}?token=<jwt>

The role encoded in the token decides what this socket may send. Every outbound
event goes through app/ws/fanout.filter_event; nothing writes to the socket
directly. A victim token can therefore never receive assessment data even if a
future handler tries to send it.

P0 scope is the echo required by the gate. Streaming audio, resume and barge-in
land in P1/P2.
"""

import json
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from ..core.security import decode_token
from .events import ROLES
from .fanout import LeakageError, filter_event

router = APIRouter(tags=["ws"])


class ConnectionRegistry:
    """In-process registry of (connection_id, role) per session.

    One process, so a dict is enough. A multi-process deployment would need a
    shared broker, which is EXT-111 and deferred.
    """

    def __init__(self) -> None:
        self._sockets: Dict[str, Dict[str, Tuple[WebSocket, str]]] = {}

    def add(self, session_id: str, connection_id: str, socket: WebSocket, role: str) -> None:
        self._sockets.setdefault(session_id, {})[connection_id] = (socket, role)

    def remove(self, session_id: str, connection_id: str) -> None:
        self._sockets.get(session_id, {}).pop(connection_id, None)

    def subscribers(self, session_id: str) -> List[Tuple[str, str]]:
        return [(cid, role) for cid, (_, role) in self._sockets.get(session_id, {}).items()]

    def socket(self, session_id: str, connection_id: str) -> WebSocket:
        return self._sockets[session_id][connection_id][0]


registry = ConnectionRegistry()


async def send_event(session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    """Fan one event out to every subscriber that is allowed to receive it."""
    for connection_id, role in registry.subscribers(session_id):
        event = filter_event(role, event_type, payload)
        if event is None:
            continue
        await registry.socket(session_id, connection_id).send_text(json.dumps(event))


@router.websocket("/ws/session/{session_id}")
async def session_socket(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
) -> None:
    try:
        claims = decode_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    role = claims.get("role")
    if role not in ROLES:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    connection_id = f"{claims.get('sub')}:{id(websocket)}"
    await websocket.accept()
    registry.add(session_id, connection_id, websocket, role)

    try:
        while True:
            message = await websocket.receive_text()
            # P0 gate: echo. The dialogue turn loop is wired in P1.
            try:
                inbound = json.loads(message)
            except json.JSONDecodeError:
                inbound = {"type": "echo", "text": message}

            await send_event(
                session_id,
                "session.status",
                {
                    "state": inbound.get("state", "S0"),
                    "consent": inbound.get("consent", "pending"),
                    "lang": inbound.get("lang", "hi"),
                    "human_joined": False,
                },
            )
    except WebSocketDisconnect:
        pass
    except LeakageError:
        # A payload bound for a victim contained assessment data. Close rather
        # than deliver it, and let the test suite surface the bug.
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        registry.remove(session_id, connection_id)
