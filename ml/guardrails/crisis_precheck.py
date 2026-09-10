"""Synchronous crisis pre-check.

Pure module: standard library only, no I/O, no model. Runs BEFORE dialogue
policy on every victim utterance (root CLAUDE.md invariant 2). Budget is
<= 0.05 s per docs/contracts/CONTRACTS.md section 8; this is substring matching
over a short utterance, so it is far inside that.

A match forces state SX, the fixed approved script, Critical priority and
immediate human takeover. Intake never resumes automatically.

Recall is favoured over precision. Only an explicit negation suppresses a match
("I would never kill myself"). Third-party attribution is recorded as context
but does NOT suppress: "he told me to kill myself" is still a crisis. Everything
suppressed is still returned so a human sees it.
"""

from typing import Any, Dict, List, Tuple

from .lexicons.crisis import (
    ATTRIBUTION_EN,
    ATTRIBUTION_HI,
    CONTEXT_WINDOW,
    CRISIS_EN,
    CRISIS_HI,
    CRISIS_HINGLISH,
    NEGATIONS_EN,
    NEGATIONS_HI,
)

__all__ = ["check"]

_ALL_TERMS: Tuple[Tuple[str, str], ...] = tuple(
    [(term, "en") for term in CRISIS_EN]
    + [(term, "hi") for term in CRISIS_HI]
    + [(term, "hinglish") for term in CRISIS_HINGLISH]
)

_NEGATIONS = tuple(NEGATIONS_EN) + tuple(NEGATIONS_HI)
_ATTRIBUTIONS = tuple(ATTRIBUTION_EN) + tuple(ATTRIBUTION_HI)


def _context(text: str, start: int, end: int) -> str:
    return text[max(0, start - CONTEXT_WINDOW) : min(len(text), end + CONTEXT_WINDOW)]


def check(utterance: str) -> Dict[str, Any]:
    """Return the crisis decision for one victim utterance.

    {
      "crisis": bool,          # True forces SX unconditionally
      "matches": [...],        # terms that fired
      "suppressed": [...],     # terms found but explicitly negated
      "lexicon_version": str,
    }
    """
    result: Dict[str, Any] = {
        "crisis": False,
        "matches": [],
        "suppressed": [],
        "lexicon_version": LEXICON_VERSION,
    }
    if not utterance:
        return result

    haystack = utterance.casefold()
    matches: List[Dict[str, str]] = []
    suppressed: List[Dict[str, str]] = []

    for term, lang in _ALL_TERMS:
        needle = term.casefold()
        index = haystack.find(needle)
        while index != -1:
            window = _context(haystack, index, index + len(needle))
            entry = {"term": term, "lang": lang}
            if any(att.casefold() in window for att in _ATTRIBUTIONS):
                entry["context"] = "attributed_to_third_party"

            if any(neg.casefold() in window for neg in _NEGATIONS):
                entry["reason"] = "negated"
                suppressed.append(entry)
            else:
                matches.append(entry)
            index = haystack.find(needle, index + len(needle))

    result["matches"] = matches
    result["suppressed"] = suppressed
    result["crisis"] = bool(matches)
    return result


LEXICON_VERSION = "crisis-v1-unreviewed"
