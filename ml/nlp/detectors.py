"""Detector interfaces producing per-dimension scores and confidences.

Every detector returns evidence turn ids. CONTRACTS.md section 3 requires every
assessment field to be traceable to the utterance that produced it; a detector
that cannot cite evidence must return a confidence of 0.
"""

from typing import Any, Dict, List, Protocol

DIMENSIONS = ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9")


class Detector(Protocol):
    dimension: str

    def score(self, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return {"dimension", "score" 0-100, "confidence" 0-1, "evidence_turn_ids"}."""
        ...


class AbstainingDetector:
    """Default detector: scores nothing and reports zero confidence.

    Wiring this in keeps the pipeline honest before real detectors exist. The
    SVI engine then abstains and returns needs_human instead of a fabricated
    number.
    """

    def __init__(self, dimension: str) -> None:
        self.dimension = dimension

    def score(self, turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "score": 0.0,
            "confidence": 0.0,
            "evidence_turn_ids": [],
        }
