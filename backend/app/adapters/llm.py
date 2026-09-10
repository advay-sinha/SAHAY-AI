"""LLM adapter.

The complete dialogue must run with LLM_PROVIDER=mock (root CLAUDE.md section 5).
An external LLM is EXT-107, PROPOSED and optional at P2.

The LLM only ever rephrases an intent the state machine already chose. It never
chooses a state, never picks a question, and its output always passes through
guardrails.validate before synthesis.
"""

from typing import Optional, Protocol


class LLMProvider(Protocol):
    name: str

    def phrase(self, intent: str, licensed_question: Optional[str], lang: str) -> Optional[str]:
        """Return a rephrasing of the licensed question, or None to use the fallback."""
        ...


class MockLLM:
    """Returns None, so every turn uses its pre-written fallback.

    This is the default. It makes the fallback path the tested path rather than
    an untested emergency route.
    """

    name = "mock"

    def phrase(self, intent: str, licensed_question: Optional[str], lang: str) -> Optional[str]:
        return None


def get_provider(name: str) -> LLMProvider:
    if name == "mock":
        return MockLLM()
    raise ValueError(
        f"LLM provider {name!r} is not available. An external LLM is EXT-107, PROPOSED."
    )
