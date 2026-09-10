"""Case, queue, decision and timeline routes.

Safety-critical rules on this router:
  * Every route requires a valid Bearer token (app/core/auth.py). Backend RBAC
    is authoritative; the console's role-based navigation is convenience only.
  * Console routes accept executive and supervisor tokens. A victim token gets
    403 here, even though it is a valid token.
  * GET /cases/{id}/timeline is the one route a victim token may also read, and
    it must carry no assessment field.
  * POST /cases/{id}/override requires a written reason, enforced server-side.

Supervisor-only endpoints (reassignment, override review, cross-case audit) are
BE-021 in HANDOVER.md, P3. When they land they use `require_supervisor`.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.auth import Principal, require_console, require_timeline_reader
from ..schemas.contracts import DecisionRequest, OverrideRequest, VictimTimeline
from ..services.decisions import OverrideReasonRequired, validate_override

router = APIRouter(tags=["cases"])


@router.get("/queue")
async def queue(principal: Principal = Depends(require_console)) -> List[dict]:
    """Band-ranked case summaries. Empty until case persistence lands in P2.

    Returning an empty list (rather than 501) makes this the console's first
    authenticated request: a 200 proves the Bearer token was accepted.
    """
    return []


@router.get("/cases/{case_id}")
async def get_case(case_id: str, principal: Principal = Depends(require_console)):
    """Full escalation packet."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "case packet lands in P2")


@router.post("/cases/{case_id}/claim")
async def claim_case(case_id: str, principal: Principal = Depends(require_console)):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "claim lands in P2")


@router.post("/cases/{case_id}/decisions")
async def record_decision(
    case_id: str, body: DecisionRequest, principal: Principal = Depends(require_console)
):
    """A human decision. Written to decisions_human, never to decisions_ai."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "decisions land in P2")


@router.post("/cases/{case_id}/override")
async def override_band(
    case_id: str, body: OverrideRequest, principal: Principal = Depends(require_console)
):
    try:
        validated = validate_override(body.band, body.reason)
    except OverrideReasonRequired as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        f"override persistence lands in P2 (validated: {validated})",
    )


@router.post("/cases/{case_id}/takeover")
async def takeover(case_id: str, principal: Principal = Depends(require_console)):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "takeover lands in P2")


@router.get("/cases/{case_id}/timeline", response_model=VictimTimeline)
async def get_timeline(
    case_id: str, principal: Principal = Depends(require_timeline_reader)
) -> VictimTimeline:
    """Victim-safe view. Built by services.timeline.victim_timeline, which
    projects onto an allowlist rather than stripping fields."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "timeline lands in P2")


@router.get("/cases/{case_id}/audit")
async def get_audit(case_id: str, principal: Principal = Depends(require_console)):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "audit viewer lands in P3")
