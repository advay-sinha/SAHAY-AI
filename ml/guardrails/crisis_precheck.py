"""Synchronous crisis pre-check.

Pure module: standard library only, no I/O, no model. Runs BEFORE dialogue
policy on every victim utterance (root CLAUDE.md invariant 2). Budget is
<= 0.05 s per docs/contracts/CONTRACTS.md section 8; this is substring matching
over a short utterance, so it is far inside that.

A match forces state SX, the fixed approved script, Critical priority and
immediate human takeover. Intake never resumes automatically.

Recall is favoured over precision. Only an explicit negation suppresses a match
("I would never kill myself"), and only a negation in the SAME CLAUSE as the
match: "The police never came back. I want to die." is a crisis. Third-party
attribution is recorded as context but does NOT suppress: "he told me to kill
myself" is still a crisis. Everything suppressed is still returned so a human
sees it.

Clause scoping (2026-09-11, ml/eval dev fixtures DEV-EN-010, DEV-HI-013,
DEV-HG-009): the negation window used to span sentence boundaries, so a
negation in an earlier sentence suppressed a later first-person crisis. The
window is now cut at clause breaks. This can only make the check fire MORE
often, never less. It is a guardrail change pending the type:dialogue review.
"""

import re
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


#: Clause boundaries: punctuation (including the danda) and contrastive
#: conjunctions in English, romanised Hindi and Devanagari.
_CLAUSE_BREAK = re.compile(r"[,.;:!?।\n]|\bbut\b|\blekin\b|\bmagar\b|लेकिन|मगर")


def _context(text: str, start: int, end: int) -> str:
    return text[max(0, start - CONTEXT_WINDOW) : min(len(text), end + CONTEXT_WINDOW)]


def _clause(text: str, start: int, end: int) -> str:
    """The context window cut to the clause that contains the match."""
    before = text[max(0, start - CONTEXT_WINDOW) : start]
    breaks = list(_CLAUSE_BREAK.finditer(before))
    if breaks:
        before = before[breaks[-1].end():]
    after = text[end : min(len(text), end + CONTEXT_WINDOW)]
    first = _CLAUSE_BREAK.search(after)
    if first:
        after = after[: first.start()]
    return before + text[start:end] + after


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

            clause = _clause(haystack, index, index + len(needle))
            if any(neg.casefold() in clause for neg in _NEGATIONS):
                entry["reason"] = "negated"
                suppressed.append(entry)
            else:
                matches.append(entry)
            index = haystack.find(needle, index + len(needle))

    result["matches"] = matches
    result["suppressed"] = suppressed
    result["crisis"] = bool(matches)
    return result


LEXICON_VERSION = "crisis-v1.1-unreviewed"
