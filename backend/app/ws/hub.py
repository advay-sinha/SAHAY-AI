"""In-process event hub with role-filtered, non-blocking fan-out.

Every published event goes through app/ws/fanout.filter_event once per
subscriber, so a victim connection can never receive an executive-only event,
and a victim-allowed event that carries an assessment field is dropped for that
victim even if a publisher builds it wrongly (the leak is counted and logged
without its payload).

Non-blocking: each connection owns a bounded queue drained by its own sender
task. `publish` only ever does `put_nowait`, so a slow, stalled or dead client
cannot delay assessment processing or other subscribers. A connection whose
queue fills up is closed; the client reconnects and resumes from the database,
which is the source of truth.

One process, so this is a plain dict. A multi-process deployment would need a
shared broker (EXT-111, deferred).
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from .fanout import LeakageError, filter_event

log = logging.getLogger("sahay.hub")

QUEUE_SIZE = 256


@dataclass(eq=False)
class Connection:
    connection_id: str
    session_id: str
    role: str
    send: Callable[[str], Awaitable[None]]
    close: Callable[[], Awaitable[None]]
    queue: "asyncio.Queue[str]" = field(default_factory=lambda: asyncio.Queue(QUEUE_SIZE))
    task: Optional["asyncio.Task[None]"] = None
    dropped: bool = False


class Hub:
    def __init__(self) -> None:
        self._subs: Dict[str, Dict[str, Connection]] = {}
        self.leaks_blocked = 0
        self.slow_disconnects = 0

    # -- subscription ----------------------------------------------------
    def subscribe(self, conn: Connection) -> Connection:
        self._subs.setdefault(conn.session_id, {})[conn.connection_id] = conn
        conn.task = asyncio.create_task(self._pump(conn))
        return conn

    async def unsubscribe(self, conn: Connection) -> None:
        self._subs.get(conn.session_id, {}).pop(conn.connection_id, None)
        if conn.task and not conn.task.done():
            conn.task.cancel()
            try:
                await conn.task
            except (asyncio.CancelledError, Exception):
                pass

    def subscribers(self, session_id: str) -> List[Connection]:
        return list(self._subs.get(session_id, {}).values())

    # -- delivery ----------------------------------------------------------
    async def _pump(self, conn: Connection) -> None:
        try:
            while True:
                frame = await conn.queue.get()
                await conn.send(frame)
        except asyncio.CancelledError:
            raise
        except Exception:
            # The socket is gone. Stop quietly; the reader side unsubscribes.
            conn.dropped = True

    def _enqueue(self, conn: Connection, frame: str) -> None:
        if conn.dropped:
            return
        try:
            conn.queue.put_nowait(frame)
        except asyncio.QueueFull:
            conn.dropped = True
            self.slow_disconnects += 1
            log.warning("closing slow subscriber on session %s (role=%s)", conn.session_id, conn.role)
            asyncio.create_task(self._close_quietly(conn))

    async def _close_quietly(self, conn: Connection) -> None:
        try:
            await conn.close()
        except Exception:
            pass
        await self.unsubscribe(conn)

    def publish(self, session_id: str, event_type: str, payload: Mapping[str, Any]) -> int:
        """Deliver to every permitted subscriber. Never awaits a socket.

        Returns the number of connections the event was queued for.
        """
        delivered = 0
        for conn in self.subscribers(session_id):
            try:
                event = filter_event(conn.role, event_type, payload)
            except LeakageError:
                self.leaks_blocked += 1
                log.error("blocked an assessment-bearing %s bound for a %s connection",
                          event_type, conn.role)
                continue
            if event is None:
                continue
            self._enqueue(conn, json.dumps(event, default=str))
            delivered += 1
        return delivered

    def send_to(self, conn: Connection, event_type: str, payload: Mapping[str, Any]) -> bool:
        """Deliver one event to one connection, through the same filter."""
        try:
            event = filter_event(conn.role, event_type, payload)
        except LeakageError:
            self.leaks_blocked += 1
            return False
        if event is None:
            return False
        self._enqueue(conn, json.dumps(event, default=str))
        return True


hub = Hub()
