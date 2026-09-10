"""Classifier interface.

MuRIL / IndicBERT / XLM-R weights are EXT-106, PROPOSED and deferred to P2.
Interpretable baselines (logistic regression, gradient boosting) go here too,
for the comparison table required by ml/CLAUDE.md.
"""

from typing import Dict, Protocol


class Classifier(Protocol):
    name: str

    def predict(self, text: str, lang: str) -> Dict[str, float]:
        """Return {label: probability}. Must be calibrated before it feeds the SVI."""
        ...
