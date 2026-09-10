"""Transcription interface. Standard library only; no model import at module scope."""

from typing import Any, Dict, Optional, Protocol


class Transcriber(Protocol):
    """Implemented later by a faster-whisper adapter (EXT-004, PROPOSED)."""

    def transcribe(self, pcm16: bytes, sample_rate: int = 16000, lang_hint: Optional[str] = None) -> Dict[str, Any]:
        """Return {"text", "lang", "lang_confidence", "asr_confidence", "duration_ms"}."""
        ...


class FixtureTranscriber:
    """Returns pre-recorded transcripts. Requires no download and no install.

    Used for every test and for the mock demo path so the dialogue loop can be
    exercised before EXT-004 is decided.
    """

    def __init__(self, transcripts: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._transcripts = dict(transcripts or {})

    def transcribe(self, pcm16: bytes, sample_rate: int = 16000, lang_hint: Optional[str] = None) -> Dict[str, Any]:
        key = str(len(pcm16))
        fixture = self._transcripts.get(key)
        if fixture is not None:
            return dict(fixture)
        return {
            "text": "",
            "lang": lang_hint or "hi",
            "lang_confidence": 0.0,
            "asr_confidence": 0.0,
            "duration_ms": 0,
            "source": "fixture_miss",
        }
