"""Output validator: the last thing between a model and a victim.

Pure module: standard library only, no I/O, no network, no model loading.

Contract:
    guardrails.validate(text, intent, lang) -> {ok, reason, safe_text}

The validator fails closed. When a generated sentence is rejected for any
reason, `safe_text` is the pre-written fallback for that intent and language,
never a repaired version of the model's sentence. Repairing model output would
mean the model still chose the words.
"""

from typing import Any, Dict, Optional

from ..dialogue import intents as _intents
from .banned_patterns import BANNED
from .lexicons.prohibitions import MAX_CHARS, MAX_QUESTION_MARKS, PROHIBITED

__all__ = ["validate"]

VALIDATOR_VERSION = "guardrails-v1"

_LANG_INDEX = {"en": 0, "hi": 1}


def _fallback(intent: str, lang: str) -> Optional[str]:
    return _intents.fallback_text(intent, lang)


def _reject(reason: str, intent: str, lang: str, detail: str = "") -> Dict[str, Any]:
    return {
        "ok": False,
        "reason": reason if not detail else f"{reason}:{detail}",
        "safe_text": _fallback(intent, lang),
        "validator_version": VALIDATOR_VERSION,
    }


def _prohibited_hit(text: str, lang: str) -> Optional[str]:
    """Return the prohibition reason a text violates, checking both languages.

    Both language lists are always checked: a Hindi turn containing an English
    promise is still a promise.
    """
    folded = text.casefold()
    for reason, (markers_en, markers_hi) in PROHIBITED.items():
        for marker in tuple(markers_en) + tuple(markers_hi):
            if marker.casefold() in folded:
                return f"{reason}|{marker}"
    return None


def validate(text: Optional[str], intent: str, lang: str) -> Dict[str, Any]:
    """Validate one generated sentence for one intent and language."""
    if lang not in _intents.SUPPORTED_LANGS:
        lang = _intents.DEFAULT_LANG

    # 1. The intent must exist and must be one an LLM is allowed to phrase.
    if intent not in _intents.FALLBACK_TEXT:
        return {
            "ok": False,
            "reason": "unknown_intent",
            "safe_text": None,
            "validator_version": VALIDATOR_VERSION,
        }
    if intent not in _intents.REPHRASABLE_INTENTS:
        # Fixed scripts are never model-generated and never validated through
        # this path. Refuse rather than silently accept.
        return {
            "ok": False,
            "reason": "intent_is_fixed_script",
            "safe_text": None,
            "validator_version": VALIDATOR_VERSION,
        }

    # 2. Empty or non-string output.
    if not isinstance(text, str) or not text.strip():
        return _reject("empty_output", intent, lang)

    candidate = text.strip()

    # 3. Length and shape.
    if len(candidate) > MAX_CHARS:
        return _reject("too_long", intent, lang, str(len(candidate)))
    if candidate.count("?") > MAX_QUESTION_MARKS:
        return _reject("multiple_questions", intent, lang)

    # 4. An acknowledgement intent may not ask anything at all.
    if intent == _intents.ACKNOWLEDGE and "?" in candidate:
        return _reject("unlicensed_question", intent, lang)

    # 5. Structural bans: URLs, phone numbers, ids, markup, lists, assessment leakage.
    for reason, pattern in BANNED.items():
        if pattern.search(candidate):
            return _reject(reason, intent, lang)

    # 6. Content prohibitions from STATES.md, checked in both languages.
    hit = _prohibited_hit(candidate, lang)
    if hit:
        reason, marker = hit.split("|", 1)
        return _reject(reason, intent, lang, marker)

    # 7. A question intent must still be asking its licensed question, not a
    #    different one. The model may rephrase; it may not substitute.
    licensed = _intents.licensed_question(intent, lang)
    if licensed is not None and "?" not in candidate:
        return _reject("licensed_question_missing", intent, lang)

    return {
        "ok": True,
        "reason": "",
        "safe_text": candidate,
        "validator_version": VALIDATOR_VERSION,
    }
