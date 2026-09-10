"""Dialogue states. Pure module: standard library only, no I/O.

Mirrors docs/dialogue/STATES.md. Any change here is a `type:dialogue` change:
two reviewers, one of them the dialogue-safety-reviewer agent, and STATES.md
updated in the same commit.
"""

from enum import Enum
from typing import Dict, Optional, Tuple


class State(str, Enum):
    S0_OPENING = "S0"
    S1_FREE_NARRATIVE = "S1"
    S2_IMMEDIATE_SAFETY = "S2"
    S3_MEDICAL_NEED = "S3"
    S4_WHO_AND_WHEN = "S4"
    S5_ONGOING_THREAT = "S5"
    S6_SUPPORT_NETWORK = "S6"
    S7_EXISTING_ACTION = "S7"
    S8_WHAT_THEY_WANT = "S8"
    S9_CLOSING = "S9"
    SX_CRISIS = "SX"
    SH_HUMAN_HANDOFF = "SH"


#: States whose text is a fixed, pre-approved, pre-synthesised script.
#: These are never model-generated.
FIXED_SCRIPT_STATES: Tuple[State, ...] = (
    State.S0_OPENING,
    State.S9_CLOSING,
    State.SX_CRISIS,
)

#: States that ask a licensed question and may be skipped or reordered.
QUESTION_STATES: Tuple[State, ...] = (
    State.S2_IMMEDIATE_SAFETY,
    State.S3_MEDICAL_NEED,
    State.S4_WHO_AND_WHEN,
    State.S5_ONGOING_THREAT,
    State.S6_SUPPORT_NETWORK,
    State.S7_EXISTING_ACTION,
    State.S8_WHAT_THEY_WANT,
)

#: Terminal states. SX never returns to intake.
TERMINAL_STATES: Tuple[State, ...] = (
    State.S9_CLOSING,
    State.SX_CRISIS,
    State.SH_HUMAN_HANDOFF,
)

#: Default order. The policy skips a state whose slots are already filled.
DEFAULT_ORDER: Tuple[State, ...] = (
    State.S0_OPENING,
    State.S1_FREE_NARRATIVE,
    State.S2_IMMEDIATE_SAFETY,
    State.S3_MEDICAL_NEED,
    State.S4_WHO_AND_WHEN,
    State.S5_ONGOING_THREAT,
    State.S6_SUPPORT_NETWORK,
    State.S7_EXISTING_ACTION,
    State.S8_WHAT_THEY_WANT,
    State.S9_CLOSING,
)

#: The slots a state exists to fill. A state whose slots are all present is skipped.
STATE_SLOTS: Dict[State, Tuple[str, ...]] = {
    State.S0_OPENING: (),
    State.S1_FREE_NARRATIVE: ("incident",),
    State.S2_IMMEDIATE_SAFETY: ("safety_now", "proximity_of_threat"),
    State.S3_MEDICAL_NEED: ("medical_need",),
    State.S4_WHO_AND_WHEN: ("persons", "when"),
    State.S5_ONGOING_THREAT: ("threat_ongoing",),
    State.S6_SUPPORT_NETWORK: ("isolation",),
    State.S7_EXISTING_ACTION: ("fir_status",),
    State.S8_WHAT_THEY_WANT: ("requested_support",),
    State.S9_CLOSING: (),
    State.SX_CRISIS: (),
    State.SH_HUMAN_HANDOFF: (),
}

#: S2 is the most important question in the intake and is never skipped on
#: the strength of extraction alone. It is only skipped when the victim has
#: explicitly answered it.
NEVER_SKIP_ON_INFERENCE: Tuple[State, ...] = (State.S2_IMMEDIATE_SAFETY,)

#: Target turn count for a first contact, per STATES.md.
TARGET_TURNS_MIN = 8
TARGET_TURNS_MAX = 12


def parse(value: object) -> Optional[State]:
    """Return the State for a value, or None. Accepts a State or its code."""
    if isinstance(value, State):
        return value
    try:
        return State(str(value))
    except ValueError:
        return None
