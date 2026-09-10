"""Assessment runner interface.

Normal assessment must never block the reply path (root CLAUDE.md section 5).
The local implementation uses asyncio.to_thread; Redis/RQ is EXT-111, deferred.

The crisis pre-check is NOT run here. It is synchronous and executes before
dialogue policy, in the request path.
"""

import asyncio
from typing import Any, Awaitable, Callable, Dict, Protocol


class AssessmentRunner(Protocol):
    name: str

    async def submit(self, job: Callable[..., Dict[str, Any]], *args: Any) -> Awaitable[Dict[str, Any]]:
        ...


class LocalThreadRunner:
    """Runs assessment off the event loop on the same machine."""

    name = "local"

    async def run(self, job: Callable[..., Dict[str, Any]], *args: Any) -> Dict[str, Any]:
        return await asyncio.to_thread(job, *args)

    def submit(self, job: Callable[..., Dict[str, Any]], *args: Any) -> "asyncio.Task[Dict[str, Any]]":
        """Fire and forget: the reply path does not await this."""
        return asyncio.create_task(self.run(job, *args))


def get_runner(name: str) -> LocalThreadRunner:
    if name == "local":
        return LocalThreadRunner()
    raise ValueError(f"assessment runner {name!r} is not available; Redis/RQ is EXT-111, deferred")
