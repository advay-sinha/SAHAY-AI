"""Append-only audit log, and the victim-safe timeline writer.

The audit log (HANDOVER.md section 11) is an accountability record: every
human act and system decision, with actor and time. It is append-only; nobody
may delete. It is NOT the authoritative timeline or override store — since
PC-03 (2026-09-11) those live in the dedicated `timeline_events` and
`overrides` tables. Writing to them also records an audit entry.

`dedupe_key` makes an audit event happen at most once (an acknowledgement).

Details never contain victim narrative text: only ids, codes and officer
input such as a rationale.
"""

from datetime import datetime, timezone
from collections.abc import Mapping
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.enums import TIMELINE_LABELS, TIMELINE_STAGES
from ..models import AuditLog, TimelineEvent

ACTOR_SYSTEM = "system"
ACTOR_HUMAN = "human"

__all__ = [
    "record",
    "timeline",
    "timeline_payload",
    "now",
    "TIMELINE_LABELS",
    "ACTOR_SYSTEM",
    "ACTOR_HUMAN",
    "UnsafeAuditDetail",
]


class UnsafeAuditDetail(ValueError):
    """Raised without echoing a rejected audit key or value."""


# Keys are normalized with separators removed before comparison. Keep this
# list limited to raw narrative and authentication/configuration material;
# structured ids, codes, counts, timestamps and fixed reason codes are valid
# accountability metadata.
_PROHIBITED_DETAIL_KEYS = frozenset(
    {
        "accesstoken",
        "apikey",
        "auth",
        "authentication",
        "authorization",
        "authheader",
        "bearer",
        "connectionstring",
        "cookie",
        "credential",
        "credentials",
        "databaseurl",
        "dsn",
        "jwt",
        "llmapikey",
        "message",
        "messagetext",
        "narrative",
        "officermessage",
        "officernarrative",
        "password",
        "passwordhash",
        "passphrase",
        "rawinput",
        "rawmessage",
        "rawtext",
        "refreshtoken",
        "requestbody",
        "responsebody",
        "rationale",
        "secret",
        "secretkey",
        "sessiontoken",
        "text",
        "token",
        "transcript",
        "utterance",
        "victimmessage",
        "victimnarrative",
        "victimtext",
    }
)


def _normalized_detail_key(key: object) -> str:
    return "".join(character for character in str(key).casefold() if character.isalnum())


def _validate_detail(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if _normalized_detail_key(key) in _PROHIBITED_DETAIL_KEYS:
                raise UnsafeAuditDetail("audit detail contains prohibited data")
            _validate_detail(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _validate_detail(nested)


def now() -> datetime:
    return datetime.now(timezone.utc)


async def record(
    db: AsyncSession,
    action: str,
    *,
    case_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_kind: str = ACTOR_SYSTEM,
    detail: Optional[Dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> bool:
    """Append one audit event. Returns False if `dedupe_key` already exists."""
    _validate_detail(detail or {})
    entry = AuditLog(
        id=str(uuid4()),
        case_id=case_id,
        actor_id=actor_id,
        actor_kind=actor_kind,
        action=action,
        detail=dict(detail or {}),
        dedupe_key=dedupe_key,
        created_at=now(),
    )
    if dedupe_key is None:
        db.add(entry)
        await db.flush()
        return True
    try:
        async with db.begin_nested():
            db.add(entry)
        return True
    except IntegrityError:
        return False


async def timeline(db: AsyncSession, case_id: str, stage: str, key: Optional[str] = None,
                   actor_id: Optional[str] = None) -> Optional[TimelineEvent]:
    """Add a victim-safe stage to `timeline_events`, at most once per key.

    `key` defaults to the stage name (one per case); action_taken uses
    `action:<recommendation id>` so each confirmed action appears once.
    Returns the new row, or None if this stage/key already exists.
    """
    if stage not in TIMELINE_STAGES:
        raise ValueError(f"unknown timeline stage {stage!r}")
    row = TimelineEvent(id=str(uuid4()), case_id=case_id, stage=stage,
                        label=TIMELINE_LABELS[stage], dedupe_key=key or stage, created_at=now())
    try:
        async with db.begin_nested():
            db.add(row)
    except IntegrityError:
        return None
    await record(db, "timeline.stage_added", case_id=case_id, actor_id=actor_id,
                 actor_kind=ACTOR_HUMAN if actor_id else ACTOR_SYSTEM,
                 detail={"stage": stage, "timeline_event_id": row.id})
    return row


def timeline_payload(row: TimelineEvent) -> Dict[str, Any]:
    """timeline.update {stage, label, ts} — victim-safe by construction."""
    return {"stage": row.stage, "label": row.label, "ts": row.created_at.isoformat()}
