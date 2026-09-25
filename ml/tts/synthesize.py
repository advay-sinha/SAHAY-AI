"""Speech synthesis interface.

EXT-103 (approved 2026-09-24): fixed scripts use human-recorded audio; validated
generated turns may use a built-in offline OS voice. No TTS model is downloaded, so
the demo path needs no online TTS.

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
