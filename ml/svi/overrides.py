"""Hard override and abstention rules for the SVI.

Rules beat weights. Standard library only, no I/O.
See docs/contracts/CONTRACTS.md section 7 and root CLAUDE.md invariants 5 and 6.
"""

from typing import Dict, List, Mapping

# A confirmed D1/D2 at or above this score forces Critical.
CRITICAL_OVERRIDE_THRESHOLD = 70.0

# The dimension must also be reported with at least this confidence before it
# is treated as "confirmed". A low-confidence signal routes to needs_human
# instead of forcing a band.
CRITICAL_OVERRIDE_MIN_CONFIDENCE = 0.60

# Aggregate confidence below this floor suppresses the score entirely.
CONFIDENCE_FLOOR = 0.45

OVERRIDE_DIMENSIONS = ("D1", "D2")


def abstention_reasons(
    aggregate_confidence: float,
    quality: Mapping[str, object],
) -> List[str]:
    """Return the reasons why no score may be produced. Empty means scoring is allowed."""
    reasons: List[str] = []

    if bool(quality.get("consent_declined", False)):
        reasons.append("consent_declined")
    if aggregate_confidence < CONFIDENCE_FLOOR:
        reasons.append("aggregate_confidence_below_floor")
    if bool(quality.get("poor_audio", False)):
        reasons.append("poor_audio_quality")
    if bool(quality.get("low_language_confidence", False)):
        reasons.append("low_language_confidence")
    # Text-channel equivalents of poor audio. Both only ever ADD abstention.
    if bool(quality.get("poor_input_quality", False)):
        reasons.append("poor_input_quality")
    if bool(quality.get("conflicting_evidence", False)):
        reasons.append("conflicting_evidence")
    # PC-08: an audio channel whose acoustic dimension was not measured
    # (runtime failure, no model) abstains; it is never renormalised.
    if bool(quality.get("acoustic_not_measured", False)):
        reasons.append("acoustic_not_measured")

    return reasons


def critical_overrides(
    dimension_scores: Mapping[str, float],
    confidences: Mapping[str, float],
) -> List[str]:
    """Return the identifiers of confirmed D1/D2 overrides that force Critical."""
    applied: List[str] = []
    for dim in OVERRIDE_DIMENSIONS:
        score = dimension_scores.get(dim)
        conf = confidences.get(dim)
        if score is None or conf is None:
            continue
        if score >= CRITICAL_OVERRIDE_THRESHOLD and conf >= CRITICAL_OVERRIDE_MIN_CONFIDENCE:
            applied.append(f"{dim}_confirmed_forces_critical")
    return applied


def danger_confirmed_override(quality: Mapping[str, object]) -> List[str]:
    """Confirmed immediate danger or a crisis interrupt forces Critical regardless of score."""
    applied: List[str] = []
    if bool(quality.get("immediate_danger_confirmed", False)):
        applied.append("immediate_danger_confirmed_forces_critical")
    if bool(quality.get("crisis_interrupt_fired", False)):
        applied.append("crisis_interrupt_forces_critical")
    return applied


def merged_overrides(
    dimension_scores: Mapping[str, float],
    confidences: Mapping[str, float],
    quality: Mapping[str, object],
) -> List[str]:
    seen: Dict[str, None] = {}
    for item in danger_confirmed_override(quality) + critical_overrides(dimension_scores, confidences):
        seen.setdefault(item, None)
    return list(seen)
