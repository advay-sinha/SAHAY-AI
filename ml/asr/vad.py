"""Voice-activity detection interface.

Silero VAD (EXT-005) is PROPOSED. The approved-today fallback is a manual
whole-utterance submit button, which requires no VAD at all.

Endpoint target: ~700 ms of silence (CONTRACTS.md section 8).
"""

from typing import Protocol

SILENCE_ENDPOINT_MS = 700
FRAME_MS = 500
SAMPLE_RATE = 16000


class VoiceActivityDetector(Protocol):
    def is_speech(self, frame_pcm16: bytes) -> bool:
        ...


class AlwaysSpeechVAD:
    """Degenerate VAD used with the manual submit fallback."""

    def is_speech(self, frame_pcm16: bytes) -> bool:
        return True
