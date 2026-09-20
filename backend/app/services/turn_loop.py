"""Turn orchestration.

The order of operations here is a safety invariant, not an implementation
detail (root CLAUDE.md invariants 1 and 2):

    1. crisis pre-check          synchronous, before anything else
    2. dialogue policy           deterministic, chooses one approved intent
    3. LLM phrasing              optional, may only rephrase that intent
    4. guardrail validation      every generated sentence, before synthesis
    5. TTS                       only validated text or an approved fixed script

Normal assessment runs on a parallel path and never blocks steps 1-5.

This module imports the pure ml modules and nothing heavier, so the reply path
carries no ML dependency.
"""

from typing import Any, Dict, Mapping, Optional

from ml.dialogue import next as dialogue_next
from ml.dialogue.intents import is_speakable
from ml.guardrails import crisis_check, validate

from ..adapters.llm import LLMProvider

#: Latency budget per stage, from CONTRACTS.md section 8.
BUDGET_MS = {
    "vad_endpoint": 700,
    "asr_final": 600,
    "safety_precheck": 50,
    "dialogue_policy": 10,
    "llm_phrasing": 800,
    "output_validator": 20,
    "tts_first_chunk": 500,
    "total": 3000,
}


class FixedScriptUnavailable(RuntimeError):
    """A fixed script was required but no approved text exists for it.

    The system fails closed: nothing unreviewed is ever spoken to a victim.
    S0, S9 and SX are outstanding (docs/dialogue/STATES.md, Team A / A2).
    """


def plan_turn(
    state: Any,
    slots: Mapping[str, Any],
    utterance: str,
    safety_flags: Optional[Mapping[str, Any]] = None,
    llm: Optional[LLMProvider] = None,
) -> Dict[str, Any]:
    """Produce the assistant's next turn.

    Returns the turn plus the audit trail the console needs to see what the
    assistant said and why it said it.
    """
    flags = dict(safety_flags or {})

    # 1. Crisis pre-check. Synchronous, before dialogue policy, always.
    precheck = crisis_check(utterance)
    if precheck["crisis"]:
        flags["crisis"] = True

    # 2. Deterministic policy picks the state and the single licensed intent.
    decision = dialogue_next(state, slots, utterance, flags)

    result: Dict[str, Any] = {
        "next_state": decision["next_state"],
        "intent": decision["intent"],
        "lang": decision["lang"],
        "crisis": bool(flags.get("crisis")),
        "crisis_evidence": precheck["matches"],
        "crisis_suppressed": precheck["suppressed"],
        "fixed_script": decision["fixed_script"],
        "was_fallback": True,
        "guardrail_reason": "",
        "text": None,
    }

    # A crisis forces Critical priority and immediate human takeover, and
    # intake never resumes automatically.
    if result["crisis"]:
        result["force_band"] = "Critical"
        result["request_takeover"] = True
        result["resume_intake"] = False

    # 3. Fixed scripts are never model-generated and never validated through
    #    the guardrail path. They are spoken verbatim or not at all.
    if decision["fixed_script"]:
        if not decision["script_available"]:
            raise FixedScriptUnavailable(
                f"state {decision['next_state']} requires an approved fixed script in "
                f"{decision['lang']}, and none is recorded"
            )
        result["text"] = decision["fallback_text"]
        return result

    # Normal intent text is victim-facing only after its language review is
    # approved. This gate precedes both model phrasing and raw fallback use.
    if not is_speakable(decision["lang"]):
        return result

    fallback = decision["fallback_text"]

    # 4. LLM phrasing is optional. With LLM_PROVIDER=mock this returns None and
    #    the fallback is used, which is the default demo path.
    candidate = None
    if llm is not None and decision["rephrasable"]:
        candidate = llm.phrase(decision["intent"], decision["licensed_question"], decision["lang"])

    if candidate is None:
        result["text"] = fallback
        result["guardrail_reason"] = "no_generated_text"
        return result

    # 5. Validate every generated sentence before synthesis. On failure use the
    #    pre-written fallback, never a repaired version of the model's sentence.
    verdict = validate(candidate, decision["intent"], decision["lang"])
    if verdict["ok"]:
        result["text"] = verdict["safe_text"]
        result["was_fallback"] = False
    else:
        result["text"] = verdict["safe_text"] or fallback
        result["guardrail_reason"] = verdict["reason"]

    return result
