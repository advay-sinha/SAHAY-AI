"""AI recommendations and human decisions, kept apart.

Root CLAUDE.md invariant 4: a human decides every recommended action, and the
record must never read as though a machine decided. `decisions_ai` and
`decisions_human` are separate tables and separate payloads; nothing in this
module merges them into one object.

Standard library only.
"""

from typing import Any, Dict, List, Optional

DECISION_CONFIRM = "confirm"
DECISION_MODIFY = "modify"
DECISION_REJECT = "reject"
DECISIONS = (DECISION_CONFIRM, DECISION_MODIFY, DECISION_REJECT)

#: A recommendation is always presented as awaiting a decision, never as taken.
STATUS_AWAITING = "awaiting_decision"
STATUS_DECIDED = "decided"


class OverrideReasonRequired(ValueError):
    """A band override without a reason is refused server-side."""


class InvalidDecision(ValueError):
    pass


def recommendation_payload(
    action_id: str,
    action_type: str,
    rationale: str,
    policy_citations: List[str],
    confidence: float,
) -> Dict[str, Any]:
    """An AI recommendation. It carries no decision field and no officer field."""
    return {
        "action_id": action_id,
        "action_type": action_type,
        "rationale": rationale,
        "policy_citations": list(policy_citations),
        "confidence": confidence,
        "status": STATUS_AWAITING,
        "decided_by_machine": False,
    }


def human_decision_payload(
    action_id: str,
    decision: str,
    rationale: str,
    officer_id: str,
) -> Dict[str, Any]:
    """A human decision. Separate record, separate table, always names a person."""
    if decision not in DECISIONS:
        raise InvalidDecision(f"decision must be one of {DECISIONS}, got {decision!r}")
    if not officer_id:
        raise InvalidDecision("a human decision must name the officer who made it")
    return {
        "action_id": action_id,
        "decision": decision,
        "rationale": rationale,
        "officer_id": officer_id,
        "status": STATUS_DECIDED,
    }


def validate_override(band: str, reason: Optional[str]) -> Dict[str, Any]:
    """POST /cases/{id}/override — reason is REQUIRED (CONTRACTS.md section 4)."""
    if not reason or not str(reason).strip():
        raise OverrideReasonRequired("a band override requires a written reason")
    return {"band": band, "reason": str(reason).strip()}
