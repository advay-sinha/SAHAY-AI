"""Voice-activity detection interface.

Silero VAD is approved through EXT-118 and runs in ml/runtime (GatedTranscriber). The manual
whole-utterance submit button remains the fallback, which requires no VAD at all.

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
