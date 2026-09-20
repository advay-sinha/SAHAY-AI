"""Dimension definitions for the Stress Vulnerability Index.

Standard library only. No I/O. See docs/contracts/CONTRACTS.md section 7.
Weights are PROVISIONAL and pending expert calibration; the console must
label them as such.
"""

from typing import Dict, Tuple

# Ordered so that breakdown output is deterministic.
DIMENSION_ORDER: Tuple[str, ...] = ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9")

DIMENSION_LABELS: Dict[str, str] = {
    "D1": "Immediate safety threat",
    "D2": "Crisis / self-harm language",
    "D3": "Fear, intimidation, threats",
    "D4": "Acute distress (acoustic + emotional)",
    "D5": "Trauma-associated indicators",
    "D6": "Social isolation, boycott, displacement",
    "D7": "Medical urgency",
    "D8": "Legal urgency",
    "D9": "Communication safety",
}

WEIGHTS: Dict[str, float] = {
    "D1": 0.22,
    "D2": 0.18,
    "D3": 0.13,
    "D4": 0.12,
    "D5": 0.08,
    "D6": 0.08,
    "D7": 0.08,
    "D8": 0.06,
    "D9": 0.05,
}

WEIGHTS_ARE_PROVISIONAL = True

SCORE_MIN = 0.0
SCORE_MAX = 100.0

#: Identifies the scoring rule that produced a stored assessment (PC-08,
#: lead decision 2026-09-11: renormalisation over structurally unavailable
#: dimensions). Bump it whenever weights, thresholds or normalisation change.
SCORING_VERSION = "svi-2026.09-pc08"

#: Dimensions that may be declared structurally unavailable for a channel.
#: Only D4 (acoustic distress) has no measurement path on a typed channel.
STRUCTURALLY_UNAVAILABLE_ALLOWED: Tuple[str, ...] = ("D4",)

# Band lower bounds (inclusive). HANDOVER.md section 7 writes the bands as
# 0-29, 30-54, 55-74, 75-100; the score is continuous, so a value belongs to
# the highest band whose lower bound it reaches (54.5 is Moderate, not a gap).
BANDS: Tuple[Tuple[float, str], ...] = (
    (75.0, "Critical"),
    (55.0, "High"),
    (30.0, "Moderate"),
    (0.0, "Low"),
)


def band_for(svi: float) -> str:
    """Return the band label for a 0-100 SVI value."""
    for low, label in BANDS:
        if svi >= low:
            return label
    return "Low"
