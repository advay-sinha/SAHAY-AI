"""The prediction firewall. Standard library only.

Rule: nothing that authors, validates, assigns, reviews, adjudicates or
prepares a freeze may load a module that can produce a prediction. If the
tooling could score a sample, somebody eventually would, and an evaluation set
whose outcomes were seen before freeze is not evidence — it is a regression
suite with a better name.

The list below is the set of import paths that constitute a prediction. It
covers the pipeline entry point, the detectors, the crisis pre-check, the SVI
engine, the guardrail validator, the recommendation logic, the evaluation
predictor and the backend assessment adapters. ``ml.guardrails`` is listed as a
package because importing any submodule of it executes
``ml/guardrails/__init__.py``, which loads the validator and the pre-check —
that is why ``blind/normalize.py`` exists instead of reusing
``ml.guardrails.normalize``.

``assert_clean()`` is called from the command-line entry points, not from
library code: a test process legitimately has the pipeline imported by other
test modules, so the real proof is ``ml/tests/test_blind_freeze.py`` running
each command in a clean subprocess and inspecting ``sys.modules`` afterwards.
"""

import sys
from typing import List, Tuple

#: Import paths that count as a prediction capability.
FORBIDDEN_MODULES: Tuple[str, ...] = (
    "ml.assessment",
    "ml.nlp.detectors",
    "ml.nlp.classifiers",
    "ml.nlp.recommend",
    "ml.guardrails",
    "ml.guardrails.crisis_precheck",
    "ml.guardrails.validator",
    "ml.guardrails.rules",
    "ml.svi",
    "ml.svi.engine",
    "ml.svi.dimensions",
    "ml.svi.overrides",
    "ml.eval.predict",
    "ml.eval.checks",
    "ml.eval.redteam",
    "ml.eval.svi_sensitivity",
    "ml.eval.evaluate",
    "backend.app.services.assessment",
    "backend.app.adapters.assessment",
)


class FirewallError(Exception):
    """A prediction module was loaded where predictions are forbidden."""


def loaded() -> List[str]:
    """Which forbidden modules are present in this interpreter, sorted."""
    return sorted(name for name in FORBIDDEN_MODULES if name in sys.modules)


def assert_clean(context: str = "blind-corpus command") -> None:
    """Raise if a prediction module is loaded. Names modules, never content."""
    present = loaded()
    if present:
        raise FirewallError(f"{context}: prediction modules are loaded before freeze: {', '.join(present)}")
