"""Acoustic feature interface feeding dimension D4 (acute distress).

No numpy/librosa/torch dependency is approved. This defines the shape the D4
scorer consumes so the SVI engine can be tested against fixtures now.
"""

from typing import Dict, Protocol


class FeatureExtractor(Protocol):
    def extract(self, pcm16: bytes, sample_rate: int = 16000) -> Dict[str, float]:
        """Return {"f0_mean", "f0_std", "rms_mean", "speech_rate", "pause_ratio", "jitter"}."""
        ...


FEATURE_NAMES = ("f0_mean", "f0_std", "rms_mean", "speech_rate", "pause_ratio", "jitter")
