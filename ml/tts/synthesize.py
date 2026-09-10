"""Speech synthesis interface.

No TTS model or voice is approved (EXT-103, PROPOSED). Fixed scripts are
pre-synthesised rather than generated at runtime, so the demo path needs no
online TTS.

Nothing may be synthesised unless guardrails.validate returned ok, or the text
is an APPROVED fixed script.
"""

from typing import Protocol

FIRST_CHUNK_TARGET_MS = 500


class Synthesizer(Protocol):
    def synthesize(self, text: str, lang: str) -> bytes:
        ...


class NullSynthesizer:
    """Produces no audio. The client falls back to displaying the text."""

    def synthesize(self, text: str, lang: str) -> bytes:
        return b""
