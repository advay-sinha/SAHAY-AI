"""Queue, escalation packet and executive actions.

Every route requires a valid Bearer token (app/core/auth.py); backend RBAC is
authoritative. Console READ routes accept executive and supervisor tokens.
Console WRITE routes accept executive tokens only: the supervisor view is
read-only (PC-06, deferred). A victim token gets 403 on both. The victim-safe
timeline additionally accepts a victim token, but only for the victim's own
case.

Every write commits once, then publishes its events (after commit) and never
waits for assessment.

Lead decisions of 2026-09-11 (docs/contracts/PROPOSED_CHANGES.md):
  PC-01  POST /cases/{id}/alerts/{alert_id}/ack is frozen.
  PC-07  POST /cases/{id}/messages is frozen, with strict limits.
  PC-06  Supervisor-only endpoints (reassignment, override review) deferred.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import (
    Principal,
    ensure_session_access,
    require_console,
    require_executive,
    require_timeline_reader,
)
from ..core.db import get_session
from ..models import Case
from ..core.errors import NotFound
from ..schemas.contracts import (
    AlertAckResponse,
    DecisionRequest,
    OfficerMessageRequest,
    OfficerMessageResponse,
    OverrideRequest,
    VictimTimeline,
)
from ..services import casework, packet
from ..services.events import publish

router = APIRouter(tags=["cases"])


@router.get("/queue")
async def get_queue(
    principal: Principal = Depends(require_console), db: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    """Band-ranked; critical unacknowledged alerts first. Codes only, no narrative."""
    return await packet.queue(db)


@router.get("/cases/{case_id}")
async def get_case(
    case_id: str, principal: Principal = Depends(require_console), db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """Full escalation packet (HANDOVER.md section 14)."""
    return await packet.packet(db, case_id)


@router.post("/cases/{case_id}/claim")
async def claim_case(
    case_id: str, principal: Principal = Depends(require_executive), db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    case, out = await casework.claim(db, case_id, principal.subject)
    await db.commit()
    publish(case.session_id, case.id, out)
    return {"case_id": case.id, "status": case.status, "assigned_officer_id": case.claimed_by}


@router.post("/cases/{case_id}/alerts/{alert_id}/ack", response_model=AlertAckResponse)
async def acknowledge_alert(
    case_id: str, alert_id: str,
    principal: Principal = Depends(require_executive), db: AsyncSession = Depends(get_session),
) -> AlertAckResponse:
    """PC-01 (frozen). Idempotent; changes neither the assessment nor the
    victim timeline, and publishes nothing to the victim."""
    alert = await casework.acknowledge(db, case_id, alert_id, principal.subject)
    await db.commit()
    return AlertAckResponse(alert_id=alert.id, case_id=alert.case_id,
                            acknowledged_by=alert.acknowledged_by,
                            acknowledged_at=alert.acknowledged_at.isoformat())


@router.post("/cases/{case_id}/decisions")
async def record_decision(
    case_id: str, body: DecisionRequest,
    principal: Principal = Depends(require_executive), db: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """A human decision. Written to decisions_human, never to decisions_ai."""
    casework.check_officer(body.officer_id, principal.subject)
    row, out = await casework.decide(db, case_id, body.action_id, body.decision, body.rationale,
                                     principal.subject)
    await db.commit()
    case = await db.get(Case, case_id)
    publish(case.session_id, case.id, out)
    return {"decision_id": row.id, "action_id": row.recommendation_id, "decision": row.decision,
            "rationale": row.rationale, "officer_id": row.officer_id}


@router.post("/cases/{case_id}/override")
async def override_band(
    case_id: str, body: OverrideRequest,
    principal: Principal = Depends(require_executive), db: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Reason REQUIRED: a missing or blank reason returns 400 (HANDOVER.md 12.4)."""
    result = await casework.override_band(db, case_id, body.band, body.reason, principal.subject)
    await db.commit()
    return result


@router.post("/cases/{case_id}/takeover")
async def takeover(
    case_id: str, principal: Principal = Depends(require_executive), db: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    case, out = await casework.takeover(db, case_id, principal.subject)
    await db.commit()
    publish(case.session_id, case.id, out)
    return {"case_id": case.id, "status": case.status}


@router.post("/cases/{case_id}/messages", response_model=OfficerMessageResponse, status_code=201)
async def officer_message(
    case_id: str, body: OfficerMessageRequest,
    principal: Principal = Depends(require_executive), db: AsyncSession = Depends(get_session),
) -> OfficerMessageResponse:
    """PC-07 (frozen, strict limits). Only the officer who claimed the case,
    after takeover (409 before). Human-written text, delivered to the victim
    as officer.message with origin "human_officer"; never AI-generated."""
    turn, out = await casework.officer_message(db, case_id, principal.subject, body.text, body.lang)
    await db.commit()
    case = await db.get(Case, case_id)
    publish(case.session_id, case.id, out)
    return OfficerMessageResponse(turn_id=turn.id, case_id=case_id, origin="human_officer",
                                  ts=turn.created_at.isoformat())


@router.get("/cases/{case_id}/timeline", response_model=VictimTimeline)
async def get_timeline(
    case_id: str, principal: Principal = Depends(require_timeline_reader),
    db: AsyncSession = Depends(get_session),
) -> VictimTimeline:
    """Victim-safe view: projected onto an allowlist, no assessment field."""
    case = await db.get(Case, case_id)
    if case is None:
        raise NotFound("case not found")
    ensure_session_access(principal, case.session_id)
    return VictimTimeline(**await packet.timeline_for(db, case_id))


@router.get("/cases/{case_id}/audit")
async def get_audit(
    case_id: str, principal: Principal = Depends(require_console), db: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    return await packet.audit_trail(db, case_id)
