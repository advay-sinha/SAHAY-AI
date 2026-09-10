"""Pure guardrail layer. Standard library only."""

from .crisis_precheck import check as crisis_check  # noqa: F401
from .validator import validate  # noqa: F401

__all__ = ["validate", "crisis_check"]
