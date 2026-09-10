"""In-process assessment runner.

Normal assessment never blocks the reply path (root CLAUDE.md section 5): the
turn handler calls `schedule(case_id)` and returns. The cycle runs as a
background task; its CPU-bound pure pipeline runs in a worker thread via
asyncio.to_thread. Redis/RQ is EXT-111 and deferred.

Cycles for one case are serialised by a per-case lock, so two turns arriving
together cannot interleave their writes. `drain()` waits for everything
scheduled so far — used by tests and the scenario runner, never by the reply
path.

The crisis pre-check does NOT run here. It is synchronous and runs in the
request path before dialogue policy.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Dict, Set

log = logging.getLogger("sahay.runner")

Job = Callable[[str], Awaitable[None]]


class LocalRunner:
    name = "local"

    def __init__(self) -> None:
        self._job: Job | None = None
        self._locks: Dict[str, asyncio.Lock] = {}
        self._tasks: Set["asyncio.Task[None]"] = set()
        self.failures = 0
        self.completed = 0

    def bind(self, job: Job) -> None:
        self._job = job

    def _lock(self, case_id: str) -> asyncio.Lock:
        if case_id not in self._locks:
            self._locks[case_id] = asyncio.Lock()
        return self._locks[case_id]

    async def _run(self, case_id: str) -> None:
        assert self._job is not None, "runner has no job bound"
        async with self._lock(case_id):
            try:
                await self._job(case_id)
                self.completed += 1
            except Exception:
                # Logged without case content. The next turn retries the cycle.
                self.failures += 1
                log.exception("assessment cycle failed for case %s", case_id)

    def schedule(self, case_id: str) -> "asyncio.Task[None]":
        """Fire and forget from the reply path's point of view."""
        task = asyncio.create_task(self._run(case_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def drain(self) -> None:
        """Wait for every scheduled cycle, including ones scheduled meanwhile."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    @staticmethod
    async def in_thread(fn, *args):
        return await asyncio.to_thread(fn, *args)


runner = LocalRunner()


def get_runner(name: str) -> LocalRunner:
    if name == "local":
        return runner
    raise ValueError(f"assessment runner {name!r} is not available; Redis/RQ is EXT-111, deferred")
