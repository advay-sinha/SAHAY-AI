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

# (inclusive_low, inclusive_high, band)
BANDS: Tuple[Tuple[float, float, str], ...] = (
    (0.0, 29.0, "Low"),
    (30.0, 54.0, "Moderate"),
    (55.0, 74.0, "High"),
    (75.0, 100.0, "Critical"),
)


def band_for(svi: float) -> str:
    """Return the band label for a 0-100 SVI value."""
    for low, high, label in BANDS:
        if low <= svi <= high:
            return label
    # Values are clamped before this is called; the guard is defensive only.
    return "Critical" if svi > SCORE_MAX else "Low"
