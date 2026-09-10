"""Deterministic dialogue policy.

Pure module: standard library only, no I/O, no network, no model loading.

Contract:
    dialogue.next(state, slots, utterance, safety_flags)
        -> {next_state, intent, licensed_question, fallback_text}

Invariants enforced here:
  * The state machine, not a model, chooses the next state and the intent.
  * A crisis flag forces SX from ANY state, unconditionally, and SX never
    returns to intake.
  * An explicit request for a human forces SH from any state.
  * Only one licensed question is ever returned.
"""

from typing import Any, Dict, Mapping, Optional, Sequence

from . import intents as _intents
from .scripts import fixed_scripts
from .states import (
    DEFAULT_ORDER,
    NEVER_SKIP_ON_INFERENCE,
    STATE_SLOTS,
    State,
    parse,
)

__all__ = ["next", "next_turn"]

DEFAULT_LANG = "hi"


def _slot_filled(slots: Mapping[str, Any], name: str) -> bool:
    value = slots.get(name)
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _explicitly_answered(slots: Mapping[str, Any], name: str) -> bool:
    """A slot counts as explicitly answered only when the victim answered it.

    Extraction from the free narrative fills `slots[name]`; the extractor also
    records the source in `slots["_sources"][name]`. S2 is never skipped on an
    inferred value.
    """
    sources = slots.get("_sources") or {}
    return _slot_filled(slots, name) and sources.get(name) == "answered"


def _is_satisfied(state: State, slots: Mapping[str, Any]) -> bool:
    required: Sequence[str] = STATE_SLOTS.get(state, ())
    if not required:
        return False
    if state in NEVER_SKIP_ON_INFERENCE:
        return all(_explicitly_answered(slots, name) for name in required)
    return all(_slot_filled(slots, name) for name in required)


def _advance(current: State, slots: Mapping[str, Any]) -> State:
    """Return the next unsatisfied state after `current` in the default order."""
    try:
        index = DEFAULT_ORDER.index(current)
    except ValueError:
        # Current state is outside the intake order (SX/SH). It is terminal.
        return current

    for candidate in DEFAULT_ORDER[index + 1 :]:
        if candidate is State.S9_CLOSING:
            return candidate
        if not _is_satisfied(candidate, slots):
            return candidate
    return State.S9_CLOSING


def _result(state: State, lang: str) -> Dict[str, Any]:
    intent = _intents.STATE_INTENT[state]
    is_fixed = intent in (
        _intents.OPENING_SCRIPT,
        _intents.CLOSING_SCRIPT,
        _intents.CRISIS_SCRIPT,
        _intents.HANDOFF_SCRIPT,
    )
    if is_fixed:
        text = fixed_scripts.text_for(state, lang)
        return {
            "next_state": state.value,
            "intent": intent,
            "licensed_question": None,
            "fallback_text": text,
            "fixed_script": True,
            "script_available": text is not None,
            "rephrasable": False,
            "lang": lang,
        }

    return {
        "next_state": state.value,
        "intent": intent,
        "licensed_question": _intents.licensed_question(intent, lang),
        "fallback_text": _intents.fallback_text(intent, lang),
        "fixed_script": False,
        "script_available": True,
        "rephrasable": intent in _intents.REPHRASABLE_INTENTS,
        "lang": lang,
    }


def next_turn(
    state: Any,
    slots: Optional[Mapping[str, Any]] = None,
    utterance: Optional[str] = None,
    safety_flags: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Choose the next state and the single intent it licenses.

    `utterance` is accepted for interface completeness but is deliberately not
    used to choose a state: crisis detection happens in the synchronous
    pre-check that populates `safety_flags`, before this function is called.
    """
    slots = dict(slots or {})
    safety_flags = dict(safety_flags or {})
    lang = str(safety_flags.get("lang") or slots.get("lang") or DEFAULT_LANG)

    current = parse(state)

    # 1. Crisis outranks everything, from any state, including SX itself.
    if bool(safety_flags.get("crisis")):
        return _result(State.SX_CRISIS, lang)

    # 2. SX never resumes intake.
    if current is State.SX_CRISIS:
        return _result(State.SX_CRISIS, lang)

    # 3. An explicit request for a human, or an escalation-driven handoff.
    if bool(safety_flags.get("request_human")) or bool(safety_flags.get("human_joined")):
        return _result(State.SH_HUMAN_HANDOFF, lang)

    if current is State.SH_HUMAN_HANDOFF:
        return _result(State.SH_HUMAN_HANDOFF, lang)

    # 4. Consent declined: no intake questions, route to a person.
    if safety_flags.get("consent") is False:
        return _result(State.SH_HUMAN_HANDOFF, lang)

    # 5. A new session with no recognised state opens with the fixed script.
    if current is None:
        return _result(State.S0_OPENING, lang)

    # 6. S1 keeps listening until the narrative slot is filled.
    if current is State.S1_FREE_NARRATIVE and not _is_satisfied(State.S1_FREE_NARRATIVE, slots):
        return _result(State.S1_FREE_NARRATIVE, lang)

    if current is State.S9_CLOSING:
        return _result(State.S9_CLOSING, lang)

    return _result(_advance(current, slots), lang)


#: Contract name. `next` shadows the builtin inside this module only; callers
#: use `dialogue.next(...)` exactly as CONTRACTS.md section 5 specifies.
next = next_turn  # noqa: A001
