"""Role-filtered event fan-out.

Server-side enforcement of root CLAUDE.md invariant 3: victim clients never
receive SVI, band, dimension, emotion, confidence, assessment or alert data.
A client-side filter is not acceptable.

Standard library only, so backend/tests/test_role_fanout.py runs with no
installed dependency.

Two independent gates, both of which must pass:
  1. The event name must be on the allowlist for the role.
  2. For a victim, no assessment field name may appear anywhere in the payload.

Gate 2 exists because gate 1 alone would let an allowed event carry a forbidden
field if someone widened a payload later.
"""

from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .events import ALLOWED_BY_ROLE, ASSESSMENT_FIELDS, ROLE_VICTIM

__all__ = ["is_allowed", "find_leaks", "filter_event", "fan_out"]


class LeakageError(Exception):
    """Raised when a payload bound for a victim contains assessment data."""


def is_allowed(role: str, event_type: str) -> bool:
    return event_type in ALLOWED_BY_ROLE.get(role, frozenset())


def find_leaks(payload: Any, _path: str = "") -> List[str]:
    """Return the dotted paths of every assessment field found at any depth."""
    leaks: List[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            path = f"{_path}.{key}" if _path else str(key)
            if str(key).casefold() in ASSESSMENT_FIELDS:
                leaks.append(path)
            leaks.extend(find_leaks(value, path))
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            leaks.extend(find_leaks(item, f"{_path}[{index}]"))
    return leaks


def filter_event(role: str, event_type: str, payload: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the event to send to this role, or None if it must not be sent.

    Raises LeakageError when a victim-allowed event carries assessment data.
    That is a programming error, not a runtime condition: it must fail the test
    suite rather than be silently stripped, so the leak is fixed at its source.
    """
    if not is_allowed(role, event_type):
        return None

    if role == ROLE_VICTIM:
        leaks = find_leaks(payload)
        if leaks:
            raise LeakageError(
                f"event {event_type!r} bound for a victim contains assessment fields: {leaks}"
            )

    return {"type": event_type, **dict(payload)}


def fan_out(
    subscribers: Iterable[Tuple[str, str]],
    event_type: str,
    payload: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Map each subscriber to the event it should receive.

    subscribers: an iterable of (connection_id, role).
    Connections that must not receive the event are absent from the result.
    """
    delivery: Dict[str, Dict[str, Any]] = {}
    for connection_id, role in subscribers:
        event = filter_event(role, event_type, payload)
        if event is not None:
            delivery[connection_id] = event
    return delivery
