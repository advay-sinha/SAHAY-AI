"""The only intended speech path: 16 kHz mono audio -> Silero VAD -> validated intervals -> Whisper.

``GatedTranscriber`` runs the VAD first and passes its intervals, unchanged, to the ASR
boundary, which validates them and decodes only those regions. When the VAD finds no speech,
Whisper is neither invoked nor even loaded. VAD output means speech presence only; it is never
read as distress, emotion, danger, crisis, an SVI input or D4. No transcript from this path is
fed to the assessment pipeline.
"""

from typing import Any

from . import audio as au
from .asr import SUPPORTED_LANGUAGES, ASRResult, WhisperASR
from .status import LOADED, RuntimeFailure
from .vad import SileroVAD


class GatedTranscriber:
    def __init__(self, vad: SileroVAD, asr: WhisperASR) -> None:
        self.vad = vad
        self.asr = asr

    def transcribe(self, samples: Any, language: str, *, sample_rate: int = au.SAMPLE_RATE) -> ASRResult:
        if language not in SUPPORTED_LANGUAGES:
            raise RuntimeFailure("unsupported_language", f"language must be one of {SUPPORTED_LANGUAGES}")
        if self.vad.status().state != LOADED:
            self.vad.load()
        speech = self.vad.intervals(samples, sample_rate)  # validates rate and shape first
        if speech.intervals and not self.asr.loaded:
            self.asr.load()  # Whisper is loaded only when there is speech to decode
        result = self.asr.transcribe(samples, language, speech.intervals, sample_rate=sample_rate)
        result.runtime["vad_speech_s"] = speech.speech_s
        return result

    def unload(self) -> None:
        self.asr.unload()
        self.vad.unload()
