"""Deterministic text detectors producing per-dimension scores and confidences.

Standard library only, no I/O. Same input, same output, every time.

Every detector returns the victim turn ids that produced its score. A dimension
with no evidence is either reported as "looked, found nothing" (score 0,
modest confidence) once enough of the conversation has been heard, or left
UNSCORED before that. D4 (acute distress) needs acoustic and emotional input
that the text channel does not have, so it is always unscored — never guessed.

Scores are severity tiers, not probabilities, and nothing here is clinically
validated.
"""

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .lexicons import (
    DIMENSION_CEILINGS,
    LEXICONS,
    NEGATION_SENSITIVE,
    NEGATION_WINDOW,
    NEGATIONS_AFTER,
    NEGATIONS_BEFORE,
    TIER_CEILINGS,
    TIER_SCORES,
)

DIMENSIONS = ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9")

#: Dimensions this module scores from text. D2 comes from the crisis pre-check;
#: D4 is unavailable on the text channel.
TEXT_DIMENSIONS = ("D1", "D3", "D5", "D6", "D7", "D8", "D9")

#: How many victim turns must have been heard before "no evidence" is itself
#: reported as a (low-confidence) zero rather than left unscored.
ABSENCE_MIN_TURNS = 3
ABSENCE_CONFIDENCE = 0.55

HIT_CONFIDENCE = 0.70
CORROBORATION_CONFIDENCE_STEP = 0.05
CORROBORATION_SCORE_STEP = 5.0
MAX_CONFIDENCE = 0.90


def _compile(term: str) -> "re.Pattern[str]":
    """ASCII terms match on word boundaries ("fir" must not match "first").
    Devanagari terms match as substrings: Python's \\b splits words at
    combining vowel signs, so it cannot be used for them."""
    if term.isascii():
        return re.compile(r"(?<![A-Za-z])" + re.escape(term.casefold()) + r"(?![A-Za-z])")
    return re.compile(re.escape(term))


_PATTERNS: Dict[str, List[Tuple["re.Pattern[str]", int, str]]] = {
    dim: [(_compile(term), tier, term) for term, tier in terms]
    for dim, terms in LEXICONS.items()
}


_CLAUSE_BREAK = re.compile(r"[,.;!?।]|\bbut\b|\blekin\b|\bpar\b|लेकिन|पर ")


def _negated(text: str, start: int, end: int) -> bool:
    """A negation only counts inside the same clause as the matched term, so
    "they didn't stop, they threatened us" is still a threat."""
    before = text[max(0, start - NEGATION_WINDOW):start]
    breaks = list(_CLAUSE_BREAK.finditer(before))
    if breaks:
        before = before[breaks[-1].end():]
    after = text[end:end + NEGATION_WINDOW]
    first_break = _CLAUSE_BREAK.search(after)
    if first_break:
        after = after[:first_break.start()]
    if any(neg in before for neg in NEGATIONS_BEFORE):
        return True
    return any(neg in after for neg in NEGATIONS_AFTER)


def match_turn(dimension: str, text: str) -> Optional[Tuple[int, List[str]]]:
    """Return (highest tier, matched terms) for one turn, or None."""
    folded = text.casefold()
    best = 0
    terms: List[str] = []
    for pattern, tier, term in _PATTERNS.get(dimension, []):
        for m in pattern.finditer(folded):
            if dimension in NEGATION_SENSITIVE and _negated(folded, m.start(), m.end()):
                continue
            terms.append(term)
            best = max(best, tier)
            break
    return (best, sorted(set(terms))) if best else None


def score_dimension(dimension: str, victim_turns: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Score one text dimension over all victim turns so far."""
    turns = list(victim_turns)
    hits: List[Tuple[str, int, List[str]]] = []
    for turn in turns:
        found = match_turn(dimension, str(turn.get("text", "")))
        if found:
            hits.append((str(turn["id"]), found[0], found[1]))

    if hits:
        top = max(tier for _, tier, _ in hits)
        distinct = len(hits)
        ceiling = DIMENSION_CEILINGS.get(dimension, {}).get(top, TIER_CEILINGS[top])
        score = min(ceiling, TIER_SCORES[top] + CORROBORATION_SCORE_STEP * (distinct - 1))
        confidence = min(MAX_CONFIDENCE, HIT_CONFIDENCE + CORROBORATION_CONFIDENCE_STEP * (distinct - 1))
        return {
            "dimension": dimension,
            "score": score,
            "confidence": round(confidence, 4),
            "evidence_turn_ids": [turn_id for turn_id, _, _ in hits],
            "matched_terms": sorted({t for _, _, ts in hits for t in ts}),
            "basis": "lexicon",
        }

    if len(turns) >= ABSENCE_MIN_TURNS:
        return {
            "dimension": dimension,
            "score": 0.0,
            "confidence": ABSENCE_CONFIDENCE,
            "evidence_turn_ids": [],
            "matched_terms": [],
            "basis": "no_evidence_after_listening",
        }

    return {
        "dimension": dimension,
        "score": None,
        "confidence": None,
        "evidence_turn_ids": [],
        "matched_terms": [],
        "basis": "not_enough_heard",
    }


def score_crisis(victim_turns: Iterable[Mapping[str, Any]], crisis_check) -> Dict[str, Any]:
    """D2 from the synchronous crisis pre-check, applied to every victim turn."""
    turns = list(victim_turns)
    evidence = [str(t["id"]) for t in turns if crisis_check(str(t.get("text", "")))["crisis"]]
    if evidence:
        return {"dimension": "D2", "score": 100.0, "confidence": MAX_CONFIDENCE,
                "evidence_turn_ids": evidence, "matched_terms": [], "basis": "crisis_precheck"}
    if len(turns) >= ABSENCE_MIN_TURNS:
        return {"dimension": "D2", "score": 0.0, "confidence": 0.60,
                "evidence_turn_ids": [], "matched_terms": [], "basis": "crisis_precheck_clear"}
    return {"dimension": "D2", "score": None, "confidence": None,
            "evidence_turn_ids": [], "matched_terms": [], "basis": "not_enough_heard"}


def unavailable(dimension: str, reason: str) -> Dict[str, Any]:
    return {"dimension": dimension, "score": None, "confidence": None,
            "evidence_turn_ids": [], "matched_terms": [], "basis": reason}


class AbstainingDetector:
    """Scores nothing. Kept for callers that need an explicit null detector."""

    def __init__(self, dimension: str) -> None:
        self.dimension = dimension

    def score(self, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"dimension": self.dimension, "score": 0.0, "confidence": 0.0,
                "evidence_turn_ids": []}
