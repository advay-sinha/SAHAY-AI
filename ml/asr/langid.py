"""Language identification interface. hi / en / hinglish for the MVP.

A low language confidence is one of the abstention triggers in svi.compute.
"""

from typing import Dict, Protocol

SUPPORTED = ("hi", "en", "hinglish")
LOW_CONFIDENCE_THRESHOLD = 0.60


class LanguageIdentifier(Protocol):
    def identify(self, text: str) -> Dict[str, float]:
        ...
