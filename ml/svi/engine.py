"""Stress Vulnerability Index engine.

Pure module: standard library only, no I/O, no network, no model loading.
Contract: svi.compute(dimension_scores, confidences, quality)
    -> {svi, band, needs_human, breakdown, overrides_applied}

The SVI is an assistive prioritisation aid. It is not a clinical, legal or
forensic determination, and a human makes every decision that follows it.
"""

from typing import Any, Dict, List, Mapping, Optional

from .dimensions import (
    DIMENSION_ORDER,
    DIMENSION_LABELS,
    SCORE_MAX,
    SCORE_MIN,
    WEIGHTS,
    WEIGHTS_ARE_PROVISIONAL,
    band_for,
)
from .overrides import CONFIDENCE_FLOOR, abstention_reasons, merged_overrides

__all__ = ["compute", "CONFIDENCE_FLOOR"]


def _clamp(value: float, low: float = SCORE_MIN, high: float = SCORE_MAX) -> float:
    return max(low, min(high, float(value)))


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _aggregate_confidence(
    confidences: Mapping[str, float],
    present: List[str],
) -> float:
    """Weight-weighted mean confidence over the dimensions actually reported.

    Dimensions that were not scored contribute nothing, but their absence
    lowers the aggregate because the weight mass they carry is treated as
    unconfident.
    """
    if not present:
        return 0.0
    total_weight = sum(WEIGHTS[dim] for dim in DIMENSION_ORDER)
    weighted = 0.0
    for dim in present:
        weighted += WEIGHTS[dim] * _clamp_confidence(confidences.get(dim, 0.0))
    return weighted / total_weight if total_weight else 0.0


def compute(
    dimension_scores: Mapping[str, float],
    confidences: Mapping[str, float],
    quality: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute the SVI, band and abstention decision.

    dimension_scores  {"D1".."D9": 0-100}. Missing dimensions are treated as unscored.
    confidences       {"D1".."D9": 0.0-1.0}. A dimension without a confidence is unscored.
    quality           optional flags:
                        poor_audio: bool
                        low_language_confidence: bool
                        consent_declined: bool
                        immediate_danger_confirmed: bool
                        crisis_interrupt_fired: bool

    Returns a dict. When needs_human is True, svi and band are None: the engine
    never fabricates a score it cannot support.
    """
    quality = dict(quality or {})

    present = [
        dim
        for dim in DIMENSION_ORDER
        if dim in dimension_scores and dim in confidences
    ]

    breakdown: List[Dict[str, Any]] = []
    for dim in DIMENSION_ORDER:
        scored = dim in present
        raw = _clamp(dimension_scores[dim]) if scored else None
        conf = _clamp_confidence(confidences[dim]) if scored else None
        breakdown.append(
            {
                "dimension": dim,
                "label": DIMENSION_LABELS[dim],
                "weight": WEIGHTS[dim],
                "weight_is_provisional": WEIGHTS_ARE_PROVISIONAL,
                "score": raw,
                "confidence": conf,
                "contribution": round(WEIGHTS[dim] * raw, 4) if scored else None,
                "scored": scored,
            }
        )

    aggregate_confidence = _aggregate_confidence(confidences, present)
    overrides_applied = merged_overrides(dimension_scores, confidences, quality)
    reasons = abstention_reasons(aggregate_confidence, quality)

    # Consent declined suppresses scoring entirely and cannot be overridden.
    consent_declined = "consent_declined" in reasons

    if consent_declined:
        return {
            "svi": None,
            "band": None,
            "needs_human": True,
            "breakdown": breakdown,
            "overrides_applied": [],
            "aggregate_confidence": round(aggregate_confidence, 4),
            "abstention_reasons": reasons,
            "weights_are_provisional": WEIGHTS_ARE_PROVISIONAL,
        }

    # A confirmed hard override still produces a Critical band even when the
    # evidence elsewhere is thin: invariant 5 beats the weighted score.
    if overrides_applied:
        weighted = sum(
            WEIGHTS[dim] * _clamp(dimension_scores[dim]) for dim in present
        )
        return {
            "svi": round(_clamp(weighted), 2),
            "band": "Critical",
            "needs_human": True,
            "breakdown": breakdown,
            "overrides_applied": overrides_applied,
            "aggregate_confidence": round(aggregate_confidence, 4),
            "abstention_reasons": [],
            "weights_are_provisional": WEIGHTS_ARE_PROVISIONAL,
        }

    if reasons:
        return {
            "svi": None,
            "band": None,
            "needs_human": True,
            "breakdown": breakdown,
            "overrides_applied": [],
            "aggregate_confidence": round(aggregate_confidence, 4),
            "abstention_reasons": reasons,
            "weights_are_provisional": WEIGHTS_ARE_PROVISIONAL,
        }

    weighted = sum(WEIGHTS[dim] * _clamp(dimension_scores[dim]) for dim in present)
    svi = round(_clamp(weighted), 2)

    return {
        "svi": svi,
        "band": band_for(svi),
        "needs_human": False,
        "breakdown": breakdown,
        "overrides_applied": [],
        "aggregate_confidence": round(aggregate_confidence, 4),
        "abstention_reasons": [],
        "weights_are_provisional": WEIGHTS_ARE_PROVISIONAL,
    }
