"""Stress Vulnerability Index engine.

Pure module: standard library only, no I/O, no network, no model loading.
Contract: svi.compute(dimension_scores, confidences, quality)
    -> {svi, band, needs_human, breakdown, overrides_applied, ...}
    plus the PC-08 normalisation record: scoring_version, available_dimensions,
    structurally_unavailable, weight_denominator, normalization_factor.

The SVI is an assistive prioritisation aid. It is not a clinical, legal or
forensic determination, and a human makes every decision that follows it.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

from .dimensions import (
    DIMENSION_ORDER,
    DIMENSION_LABELS,
    SCORE_MAX,
    SCORE_MIN,
    SCORING_VERSION,
    STRUCTURALLY_UNAVAILABLE_ALLOWED,
    WEIGHTS,
    WEIGHTS_ARE_PROVISIONAL,
    band_for,
)
from .overrides import CONFIDENCE_FLOOR, abstention_reasons, merged_overrides

__all__ = ["compute", "CONFIDENCE_FLOOR", "SCORING_VERSION"]


def _clamp(value: float, low: float = SCORE_MIN, high: float = SCORE_MAX) -> float:
    return max(low, min(high, float(value)))


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _structurally_unavailable(quality: Mapping[str, Any], dimension_scores: Mapping[str, float]) -> List[str]:
    """Validate quality["structurally_unavailable"] (PC-08).

    Only a dimension with no measurement path on the channel may be declared
    (today: D4 on a typed channel). A declared dimension must not also carry a
    score: it is either measured or structurally absent, never both.
    """
    declared: Sequence[str] = quality.get("structurally_unavailable") or ()
    out: List[str] = []
    for dim in DIMENSION_ORDER:
        if dim not in declared:
            continue
        if dim not in STRUCTURALLY_UNAVAILABLE_ALLOWED:
            raise ValueError(f"{dim} cannot be declared structurally unavailable")
        if dim in dimension_scores:
            raise ValueError(f"{dim} is declared structurally unavailable but has a score")
        out.append(dim)
    unknown = set(declared) - set(DIMENSION_ORDER)
    if unknown:
        raise ValueError(f"unknown dimensions: {sorted(unknown)}")
    return out


def compute(
    dimension_scores: Mapping[str, float],
    confidences: Mapping[str, float],
    quality: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute the SVI, band and abstention decision.

    dimension_scores  {"D1".."D9": 0-100}. Missing dimensions are treated as unscored.
    confidences       {"D1".."D9": 0.0-1.0}. A dimension without a confidence is unscored.
    quality           optional flags:
                        structurally_unavailable: ["D4"]  (PC-08; see below)
                        poor_audio: bool
                        low_language_confidence: bool
                        poor_input_quality: bool       (text channel)
                        conflicting_evidence: bool     (e.g. "safe" and "they are outside")
                        consent_declined: bool
                        immediate_danger_confirmed: bool
                        crisis_interrupt_fired: bool

    Renormalisation (PC-08, lead decision 2026-09-11). When a dimension is
    STRUCTURALLY unavailable for the channel -- it has no measurement path at
    all, as D4 acoustic distress on typed text -- its weight is removed and the
    rest are rescaled:

        weight_denominator = sum of weights of the available dimensions
        normalized_svi     = weighted_sum_available / weight_denominator

    With only D4 absent the denominator is 0.88. The absent dimension is
    reported as unavailable: never scored, never zero. A dimension that is
    available but missing (poor audio, runtime failure, low confidence) is NOT
    rescaled: its weight stays in the denominator and the abstention rules
    decide. Hard overrides apply independently of normalisation; band
    thresholds apply to the normalised value.

    Returns a dict. When needs_human is True and no override applies, svi and
    band are None: the engine never fabricates a score it cannot support.
    """
    quality = dict(quality or {})
    unavailable = _structurally_unavailable(quality, dimension_scores)
    available = [dim for dim in DIMENSION_ORDER if dim not in unavailable]
    denominator = sum(WEIGHTS[dim] for dim in available)

    present = [
        dim
        for dim in available
        if dim in dimension_scores and dim in confidences
    ]

    breakdown: List[Dict[str, Any]] = []
    for dim in DIMENSION_ORDER:
        scored = dim in present
        raw = _clamp(dimension_scores[dim]) if scored else None
        conf = _clamp_confidence(confidences[dim]) if scored else None
        is_available = dim not in unavailable
        effective = WEIGHTS[dim] / denominator if is_available else 0.0
        breakdown.append(
            {
                "dimension": dim,
                "label": DIMENSION_LABELS[dim],
                "weight": WEIGHTS[dim],
                "effective_weight": round(effective, 6),
                "weight_is_provisional": WEIGHTS_ARE_PROVISIONAL,
                "score": raw,
                "confidence": conf,
                # Contribution to the normalised SVI: contributions sum to svi.
                "contribution": round(effective * raw, 4) if scored else None,
                "scored": scored,
                "available": is_available,
                "unavailable_reason": None if is_available else "structurally_unavailable_for_channel",
            }
        )

    weighted = sum(WEIGHTS[dim] * _clamp(dimension_scores[dim]) for dim in present)
    normalized = _clamp(weighted / denominator) if present else 0.0
    # Aggregate confidence is normalised over the same denominator. An
    # available-but-unscored dimension still counts as unconfident.
    aggregate_confidence = (
        sum(WEIGHTS[dim] * _clamp_confidence(confidences.get(dim, 0.0)) for dim in present) / denominator
        if present else 0.0
    )
    overrides_applied = merged_overrides(dimension_scores, confidences, quality)
    reasons = abstention_reasons(aggregate_confidence, quality)

    base = {
        "breakdown": breakdown,
        "aggregate_confidence": round(aggregate_confidence, 4),
        "weights_are_provisional": WEIGHTS_ARE_PROVISIONAL,
        "scoring_version": SCORING_VERSION,
        "available_dimensions": available,
        "structurally_unavailable": unavailable,
        "weight_denominator": round(denominator, 6),
        "normalization_factor": round(1.0 / denominator, 6),
    }

    # Consent declined suppresses scoring entirely and cannot be overridden.
    if "consent_declined" in reasons:
        return {"svi": None, "band": None, "needs_human": True, "overrides_applied": [],
                "abstention_reasons": reasons, **base}

    # A confirmed hard override still produces a Critical band even when the
    # evidence elsewhere is thin: invariant 5 beats the weighted score.
    if overrides_applied:
        return {"svi": round(normalized, 2), "band": "Critical", "needs_human": True,
                "overrides_applied": overrides_applied, "abstention_reasons": [], **base}

    if reasons:
        return {"svi": None, "band": None, "needs_human": True, "overrides_applied": [],
                "abstention_reasons": reasons, **base}

    svi = round(normalized, 2)
    return {"svi": svi, "band": band_for(svi), "needs_human": False, "overrides_applied": [],
            "abstention_reasons": [], **base}
