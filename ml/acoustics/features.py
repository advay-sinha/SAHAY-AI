"""Acoustic feature interface feeding dimension D4 (acute distress).

Two layers (plan M12a, EXT-121):

* ``acoustics.signal``  - frame tracks (YIN F0, RMS) and quality from 16 kHz samples;
                          numpy is imported lazily, only when it runs.
* ``acoustics.prosody`` - standard-library summary features and deviation from the
                          caller's own in-session baseline.

Neither produces a D4 value. The D4 fusion rule is a separate, lead-approved step (D-8).
"""

from typing import Any, Dict, Protocol

from .prosody import FEATURE_NAMES


class FeatureExtractor(Protocol):
    def extract(self, pcm16: bytes, sample_rate: int = 16000) -> Dict[str, Any]:
        """Return prosody features keyed by ``FEATURE_NAMES``; unmeasurable values are None."""
        ...


__all__ = ["FEATURE_NAMES", "FeatureExtractor"]
