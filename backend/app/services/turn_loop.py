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

import time
from typing import Any, Dict, Mapping, Optional

from ml.dialogue import next as dialogue_next
from ml.dialogue.intents import is_speakable
from ml.dialogue.variants import hinglish_text
from ml.guardrails import crisis_check, validate
from ml.llm.meaning import keeps_meaning
from ml.llm.prompt import register_for
from ml.nlp.langid import identify

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
    # Per-stage wall time in ms (M2). Internal: intake stores it in latency_metrics; it is never sent
    # to a client. The dict is shared with ``result``, so every early return carries what was measured.
    timings: Dict[str, float] = {}
    t0 = time.perf_counter()

    # 1. Crisis pre-check. Synchronous, before dialogue policy, always.
    precheck = crisis_check(utterance)
    if precheck["crisis"]:
        flags["crisis"] = True
    t1 = time.perf_counter()
    timings["safety_precheck"] = round(1000 * (t1 - t0), 3)

    # 2. Deterministic policy picks the state and the single licensed intent.
    decision = dialogue_next(state, slots, utterance, flags)
    t2 = time.perf_counter()
    timings["dialogue_policy"] = round(1000 * (t2 - t1), 3)

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
        "timings_ms": timings,
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

    # Register: the person's own script decides it, deterministically, never a model.
    # The caller passes a session-level register (sticky across turns); a direct call
    # falls back to this utterance alone. Hinglish is only for a Hindi session and only
    # on text: a voice reply in Latin script would be read badly by the Hindi voice.
    register = flags.get("register") or register_for(decision["lang"], identify(utterance or "")["lang"])
    if register == "hinglish" and (decision["lang"] != "hi" or flags.get("voice")):
        register = decision["lang"]
    result["register"] = register
    result["review_status"] = "approved_text"
    if register == "hinglish":
        roman = hinglish_text(decision["intent"])  # reviewed, pinned text only
        if roman and validate(roman, decision["intent"], decision["lang"])["ok"]:
            fallback = roman
            result["review_status"] = "approved_hinglish"

    # 4. LLM phrasing is optional. With LLM_PROVIDER=mock this returns None and
    #    the fallback is used, which is the default demo path. The model receives
    #    only the approved sentence and the register, never the person's words.
    candidate = None
    t3 = time.perf_counter()
    if llm is not None and decision["rephrasable"]:
        candidate = llm.phrase(decision["intent"], decision["licensed_question"], decision["lang"],
                               register=register, source=decision["licensed_question"] or fallback)
    t4 = time.perf_counter()
    timings["llm_phrasing"] = round(1000 * (t4 - t3), 3)

    # Alternative wordings are English only: discard anything else here, at the safety
    # layer, whatever a provider returns. Reject multi-line or control characters outright.
    if candidate is not None and (decision["lang"] != "en" or register != "en"
                                  or not isinstance(candidate, str)
                                  or any(ord(c) < 32 for c in candidate)):
        candidate = None

    if candidate is None:
        result["text"] = fallback
        result["guardrail_reason"] = "no_generated_text"
        return result

    # 5. Validate every generated sentence before synthesis. On failure use the
    #    pre-written fallback, never a repaired version of the model's sentence.
    verdict = validate(candidate, decision["intent"], decision["lang"])
    timings["output_validator"] = round(1000 * (time.perf_counter() - t4), 3)
    # 6. The validator catches unsafe content, not a changed meaning. English
    #    rewordings must also keep every required concept of their intent.
    if verdict["ok"] and decision["lang"] == "en" and not keeps_meaning(verdict["safe_text"], decision["intent"]):
        verdict = {"ok": False, "reason": "meaning_changed", "safe_text": None}
    if verdict["ok"]:
        result["text"] = verdict["safe_text"]
        result["was_fallback"] = False
        result["review_status"] = ("approved_variant" if getattr(llm, "name", "") == "variants"
                                   else "model_generated")
    else:
        result["text"] = fallback
        result["guardrail_reason"] = verdict["reason"]

    return result
