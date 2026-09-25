"""Audio quality gate.

Poor audio is an abstention trigger: svi.compute returns needs_human and no
score (root CLAUDE.md invariant 6). The metrics come from ``acoustics.signal.quality``.
A missing measurement counts as poor, never as good.
"""

from typing import Any, Dict

SNR_FLOOR_DB = 10.0
MIN_SPEECH_MS = 800
MAX_CLIPPING_RATIO = 0.02


def is_poor(metrics: Dict[str, Any]) -> bool:
    """True when the audio is not good enough to score."""
    snr = metrics.get("snr_db")
    if snr is None or snr < SNR_FLOOR_DB:
        return True
    if (metrics.get("speech_ms") or 0.0) < MIN_SPEECH_MS:
        return True
    clipping = metrics.get("clipping_ratio")
    if clipping is None or clipping > MAX_CLIPPING_RATIO:
        return True
    return False
