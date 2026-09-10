"""Audio quality gate.

Poor audio is an abstention trigger: svi.compute returns needs_human and no
score (root CLAUDE.md invariant 6).
"""

from typing import Dict

SNR_FLOOR_DB = 10.0
MIN_SPEECH_MS = 800
MAX_CLIPPING_RATIO = 0.02


def is_poor(metrics: Dict[str, float]) -> bool:
    """True when the audio is not good enough to score."""
    if metrics.get("snr_db", 0.0) < SNR_FLOOR_DB:
        return True
    if metrics.get("speech_ms", 0.0) < MIN_SPEECH_MS:
        return True
    if metrics.get("clipping_ratio", 0.0) > MAX_CLIPPING_RATIO:
        return True
    return False
