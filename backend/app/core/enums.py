"""Canonical contract enumerations (PC-10). Single source for the backend.

Standard library only, so the no-install safety tests can import it.

Mirrors the enumerations in docs/contracts/CONTRACTS.md section 9 and
frontend/src/types/contracts.ts. backend/tests/test_contract_mirror.py fails if
any of the three disagree.

HANDOVER.md vocabulary is the authority. Documented differences:
  * pathway `emergency` — required by the problem statement ("emergency
    support", HANDOVER section 2) though absent from the HANDOVER section 11
    comment; `welfare` and `follow_up` are frozen but have no producer yet.
  * case status is not enumerated in HANDOVER; the values are the slice's
    enforced state machine;
  * timeline stage `closed` covers HANDOVER's "closed/continuing"; a
    continuing case simply has no `closed` stage yet;
  * timeline labels never name the pathway (a victim's phone may be seen by
    the person they are reporting); see CONTRACTS.md section 8.
"""

from typing import Dict, Tuple

# --- Sessions ---------------------------------------------------------------
SESSION_CHANNELS: Tuple[str, ...] = ("mobile_voice", "mobile_chat", "portal_chat", "upload")
#: Channels on which acoustic distress (D4) cannot be measured by design (PC-08).
TEXT_CHANNELS: Tuple[str, ...] = ("mobile_chat", "portal_chat")

SESSION_STATES: Tuple[str, ...] = (
    "S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "SX", "SH",
)

CONSENT_STATUSES: Tuple[str, ...] = ("granted", "declined", "pending")

# --- Cases, assessment, alerts, decisions ------------------------------------
CASE_STATUSES: Tuple[str, ...] = ("open", "claimed", "taken_over", "closed")

BANDS: Tuple[str, ...] = ("Low", "Moderate", "High", "Critical")

ALERT_TYPES: Tuple[str, ...] = ("crisis", "threat", "medical", "coercion")
ALERT_SEVERITIES: Tuple[str, ...] = ("high", "critical")

RECOMMENDATION_PATHWAYS: Tuple[str, ...] = (
    "counselling", "legal_aid", "medical", "police", "witness_protection",
    "emergency", "welfare", "follow_up",
)

DECISIONS: Tuple[str, ...] = ("confirm", "modify", "reject")

ROLES: Tuple[str, ...] = ("victim", "executive", "supervisor")

# --- Victim-safe timeline (HANDOVER VF-08) ------------------------------------
TIMELINE_STAGES: Tuple[str, ...] = (
    "request_received", "under_review", "officer_assigned",
    "action_taken", "follow_up_scheduled", "closed",
)

#: Plain-language labels. Process only: no assessment, no pathway name, no
#: promise of an outcome or a timeline.
TIMELINE_LABELS: Dict[str, str] = {
    "request_received": "Your request has been received",
    "under_review": "Your request is being reviewed",
    "officer_assigned": "An officer has been assigned",
    "action_taken": "An officer has taken action on your request",
    "follow_up_scheduled": "A follow-up has been scheduled",
    "closed": "Your request has been closed",
}

#: Turn origins (HANDOVER.md section 11). `officer` turns are written by the
#: human officer after takeover (PC-07) and reach the victim as
#: officer.message with origin OFFICER_MESSAGE_ORIGIN.
TURN_SPEAKERS: Tuple[str, ...] = ("victim", "assistant", "officer")
OFFICER_MESSAGE_ORIGIN = "human_officer"

#: Needs Human Assessment is represented as svi = null, band = null,
#: needs_human = true (never a zero, never a hidden number).
NEEDS_HUMAN_REPRESENTATION = {"svi": None, "band": None, "needs_human": True}

#: Every non-2xx body (CONTRACTS.md section 9). 422 carries a list of
#: {loc, msg}; 500 is always the fixed text below.
ERROR_SHAPE = {"detail": "string | [{loc, msg}]"}
INTERNAL_ERROR_DETAIL = "Internal error"

assert set(TIMELINE_LABELS) == set(TIMELINE_STAGES)
assert set(TEXT_CHANNELS) <= set(SESSION_CHANNELS)
