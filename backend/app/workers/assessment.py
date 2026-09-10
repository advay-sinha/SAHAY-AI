"""Background assessment job.

Runs off the reply path through the local runner. It reads turns, runs the
detectors, and computes the SVI. It never speaks to the victim and never
triggers the crisis interrupt: that is the synchronous pre-check's job, and
only the pre-check may raise SX (docs/dialogue/STATES.md).
"""

from typing import Any, Dict, List, Mapping

from ml.nlp.detectors import DIMENSIONS, AbstainingDetector
from ml.svi import compute


def run_assessment(turns: List[Mapping[str, Any]], quality: Mapping[str, Any]) -> Dict[str, Any]:
    """Score one session. Returns the svi.compute result unchanged."""
    detectors = [AbstainingDetector(dim) for dim in DIMENSIONS]

    scores: Dict[str, float] = {}
    confidences: Dict[str, float] = {}
    evidence: Dict[str, List[str]] = {}

    for detector in detectors:
        result = detector.score(list(turns))
        scores[result["dimension"]] = result["score"]
        confidences[result["dimension"]] = result["confidence"]
        evidence[result["dimension"]] = result["evidence_turn_ids"]

    outcome = compute(scores, confidences, quality)
    outcome["evidence"] = evidence
    return outcome
