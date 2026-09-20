"""Event names and the role allowlist.

Deliberately dependency-free: standard library only, no FastAPI import. That
keeps the role fan-out testable with `python -m unittest` before EXT-001 is
approved, and it keeps the most safety-critical code in the backend free of
framework coupling.

Source of truth: docs/contracts/CONTRACTS.md sections 2 and 3.
"""

from typing import Dict, FrozenSet

ROLE_VICTIM = "victim"
ROLE_EXECUTIVE = "executive"
ROLE_SUPERVISOR = "supervisor"

ROLES = (ROLE_VICTIM, ROLE_EXECUTIVE, ROLE_SUPERVISOR)

#: CONTRACTS.md section 2 — the complete set a victim client may receive.
#: This is an allowlist. An event not named here is never sent to a victim,
#: including one added later.
VICTIM_ALLOWED: FrozenSet[str] = frozenset(
    {
        "assistant.turn",
        "transcript.line",
        "session.status",
        "timeline.update",
        # PC-07 (lead decision 2026-09-11): text written by the human officer
        # after a verified takeover. Origin is always "human_officer"; it is
        # published only by services/casework.officer_message.
        "officer.message",
    }
)

#: CONTRACTS.md section 3 — executive console only.
EXECUTIVE_ONLY: FrozenSet[str] = frozenset(
    {
        "dimension.update",
        "alert.safety",
        "case.structured",
        "action.recommended",
        "safesignal.flag",
        "escalation.packet",
    }
)

ALLOWED_BY_ROLE: Dict[str, FrozenSet[str]] = {
    ROLE_VICTIM: VICTIM_ALLOWED,
    ROLE_EXECUTIVE: VICTIM_ALLOWED | EXECUTIVE_ONLY,
    ROLE_SUPERVISOR: VICTIM_ALLOWED | EXECUTIVE_ONLY,
}

#: Field names that must never appear in any payload sent to a victim, at any
#: depth. Root CLAUDE.md invariant 3.
ASSESSMENT_FIELDS: FrozenSet[str] = frozenset(
    {
        "svi",
        "band",
        "dims",
        "dimension",
        "dimensions",
        "needs_human",
        "overrides_applied",
        "confidence",
        "conf",
        "emotion",
        "emotions",
        "assessment",
        "alert",
        "alerts",
        "severity",
        "recommendation",
        "recommendations",
        "action_recommended",
        "policy_citations",
        "evidence_turn_ids",
        "breakdown",
        "aggregate_confidence",
        "risk",
        "priority",
        "safesignal",
    }
)
