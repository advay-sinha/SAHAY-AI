"""Lazy local ASR adapter: Whisper Small through faster-whisper (CTranslate2).

* The model is the pinned ``openai/whisper-small`` revision, converted locally to CTranslate2
  FP16 (see ``download.py``); it is loaded with ``local_files_only=True`` and offline switches.
* The task is always ``transcribe``. Hindi is never silently translated into English.
* The caller must name the language (``hi`` or ``en``); there is no silent auto-detection.
* One ASR worker by default. Audio is processed in memory and never retained or logged.
* No calibrated confidence exists, so none is reported: ``calibrated_confidence`` is always
  ``None``. Whisper's own log-probabilities are passed through as uncalibrated diagnostics.
* Results stay inside ``ml.runtime``; nothing here feeds the assessment pipeline or a contract.

VAD is an enforced boundary, not advice. Task 6 measured Whisper Small emitting fluent text for
silence, pure tones and synthetic non-speech when forced to decode. So the public
``WhisperASR.transcribe`` requires the Silero speech intervals (no default, ``None`` refused),
validates all of them before the first decoder call, returns ``no_speech`` without invoking
Whisper when the VAD found nothing, and hands the decoder only the samples inside each accepted
interval. Every result from it carries ``vad_gated=True``. The only ungated decode is the private
``_transcribe_ungated_for_benchmark``, reserved for ``ml.runtime.benchmark`` and labelled
``benchmark_only=True``. ``ml.runtime.pipeline.GatedTranscriber`` wires VAD to ASR.
"""

import importlib
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import audio as au, config, device as dev
from .offline import apply_offline_env
from .status import AVAILABLE, LOADED, UNAVAILABLE, RuntimeFailure, RuntimeStatus, redact

LOGICAL_ID = "whisper_small"
TASK = "transcribe"
SUPPORTED_LANGUAGES = ("hi", "en")
CUDA_COMPUTE_TYPE = "float16"
CPU_COMPUTE_TYPE = "int8"
WORKERS = 1
CONFIDENCE_NOTE = "no calibrated confidence exists for this model on SAHAY audio; diagnostics are raw and uncalibrated"
SCOPE_NOTE = ("speech presence and transcript only: no D4, emotion, distress, danger, crisis, score or routing "
              "value exists here")
REQUIRED_DERIVED_FILES = ("model.bin", "config.json", "vocabulary.json", "tokenizer.json", "preprocessor_config.json")


@dataclass
class ASRSegment:
    start: float
    end: float
    text: str
    avg_logprob: Optional[float] = None
    no_speech_prob: Optional[float] = None


@dataclass
class ASRResult:
    text: str
    requested_language: str
    task: str
    segments: List[ASRSegment]
    duration_s: float
    status: str                       # "transcribed", "decoded_no_text", "no_speech" or "no_audio"
    vad_gated: bool                   # always True from the public path; False only when benchmark_only
    intervals_detected: int
    intervals_decoded: int
    decoder_invoked: bool
    benchmark_only: bool = False
    runtime: Dict[str, Any] = field(default_factory=dict)
    detected_language: Optional[str] = None
    detected_language_probability: Optional[float] = None
    calibrated_confidence: None = None
    confidence_note: str = CONFIDENCE_NOTE
    scope_note: str = SCOPE_NOTE

    def summary(self) -> Dict[str, Any]:
        """Aggregate-only view with no transcript text: safe to print."""
        d = asdict(self)
        d.pop("text")
        d["characters"] = len(self.text)
        d["segments"] = [{"start": s.start, "end": s.end} for s in self.segments]
        return d


class FasterWhisperBackend:
    def __init__(self, directory: Path, choice: dev.DeviceChoice, compute_type: str) -> None:
        apply_offline_env()
        if choice.device == "cuda":
            # On Windows CTranslate2 takes cuBLAS 12 from the PyTorch CUDA wheel; importing torch
            # first puts its DLL directory on the search path.
            dev.import_torch()
        fw = importlib.import_module("faster_whisper")
        self.model = fw.WhisperModel(str(directory), device=choice.device, compute_type=compute_type,
                                     num_workers=WORKERS, local_files_only=True)

    def transcribe(self, samples: Any, **options: Any) -> Tuple[List[ASRSegment], Dict[str, Any]]:
        segments, info = self.model.transcribe(au.to_float32_numpy(samples), **options)
        out = [ASRSegment(round(s.start, 3), round(s.end, 3), s.text.strip(), s.avg_logprob, s.no_speech_prob)
               for s in segments]  # consuming the generator runs the decoder
        return out, {"language": info.language, "language_probability": info.language_probability}

    def close(self) -> None:
        self.model = None


BackendFactory = Callable[[Path, dev.DeviceChoice, str], Any]


class WhisperASR:
    def __init__(self, *, models_root: Optional[str] = None, device: str = "auto",
                 compute_type: Optional[str] = None, backend_factory: Optional[BackendFactory] = None,
                 manifest: Optional[Dict[str, Any]] = None, device_choice: Optional[dev.DeviceChoice] = None,
                 beam_size: int = 5) -> None:
        self._root_arg = models_root
        self._device = device
        self._compute_type = compute_type
        self._choice = device_choice
        self._factory = backend_factory or FasterWhisperBackend
        self._manifest = manifest
        self._backend: Any = None
        self.beam_size = beam_size
        self.load_seconds: Optional[float] = None

    def _directory(self) -> Path:
        manifest = self._manifest if self._manifest is not None else config.load_manifest()
        entry = config.get_model(manifest, LOGICAL_ID)
        return config.derived_dir(config.models_root(self._root_arg), entry)

    def status(self) -> RuntimeStatus:
        if self._backend is not None:
            return RuntimeStatus(LOGICAL_ID, LOADED, "speech_to_text", self._choice.device, self.compute_type,
                                 self._choice.degraded)
        try:
            directory = self._directory()
        except config.RuntimeConfigError as exc:
            return RuntimeStatus(LOGICAL_ID, UNAVAILABLE, str(exc))
        if not all((directory / f).is_file() for f in REQUIRED_DERIVED_FILES):
            return RuntimeStatus(LOGICAL_ID, UNAVAILABLE, "converted Whisper files missing; run the conversion")
        if self._factory is FasterWhisperBackend and not dev.package_available("faster_whisper"):
            return RuntimeStatus(LOGICAL_ID, UNAVAILABLE, "faster-whisper is not installed in this environment")
        return RuntimeStatus(LOGICAL_ID, AVAILABLE, "speech_to_text")

    @property
    def compute_type(self) -> Optional[str]:
        if self._compute_type:
            return self._compute_type
        if self._choice is None:
            return None
        return CUDA_COMPUTE_TYPE if self._choice.device == "cuda" else CPU_COMPUTE_TYPE

    @property
    def loaded(self) -> bool:
        return self._backend is not None

    def load(self) -> RuntimeStatus:
        if self._backend is not None:
            return self.status()
        state = self.status()
        if state.state != AVAILABLE:
            raise RuntimeFailure("unavailable", state.reason)
        directory = self._directory()
        self._choice = self._choice or dev.select_device(self._device)
        started = time.perf_counter()
        try:
            self._backend = self._factory(directory, self._choice, self.compute_type)
        except Exception as exc:
            self._backend = None
            dev.release()
            code = "resource_exhausted" if dev.is_out_of_memory(exc) else "load_failed"
            raise RuntimeFailure(code, redact(str(exc), directory.parent.parent), exc) from None
        self.load_seconds = time.perf_counter() - started
        return self.status()

    def unload(self) -> None:
        backend, self._backend = self._backend, None
        if backend is not None:
            backend.close()
            del backend
        dev.release()

    def transcribe(self, samples: Any, language: str, speech_intervals: Sequence[Tuple[float, float]], *,
                   sample_rate: int = au.SAMPLE_RATE) -> ASRResult:
        """Transcribe (never translate) only the VAD speech regions of ``samples``.

        ``speech_intervals`` is required and has no default: it is the Silero adapter's output,
        ``(start_s, end_s)`` pairs in seconds. ``None`` is refused before anything else happens.
        The whole list is validated before the first decoder call; an empty list means the VAD
        found no speech and returns a ``no_speech`` result without invoking Whisper (or even
        needing it loaded). Only the samples inside each accepted interval are handed to the
        decoder; the full recording is never decoded as a fallback.
        """
        if language not in SUPPORTED_LANGUAGES:
            raise RuntimeFailure("unsupported_language", f"language must be one of {SUPPORTED_LANGUAGES}")
        if speech_intervals is None:
            raise RuntimeFailure("vad_required", "speech_intervals from the VAD are required; None is refused")
        samples, duration = _validated_audio(samples, sample_rate)
        spans = validate_speech_intervals(speech_intervals, len(samples))
        if not spans:
            return ASRResult("", language, TASK, [], duration, "no_audio" if duration == 0 else "no_speech",
                             vad_gated=True, intervals_detected=0, intervals_decoded=0, decoder_invoked=False,
                             runtime=self._runtime_meta())
        if self._backend is None:
            raise RuntimeFailure("unavailable", "ASR is not loaded; call load() explicitly")
        started = time.perf_counter()
        segments: List[ASRSegment] = []
        info: Dict[str, Any] = {}
        try:
            for start, end in spans:  # every interval was validated before this first call
                region = samples[int(round(start * au.SAMPLE_RATE)):int(round(end * au.SAMPLE_RATE))]
                found, region_info = self._decode(region, language)
                info = info or region_info
                segments += [ASRSegment(round(s.start + start, 3), round(s.end + start, 3), s.text, s.avg_logprob,
                                        s.no_speech_prob) for s in found]
        finally:
            del samples  # nothing is retained after processing
        runtime = self._runtime_meta()
        runtime["latency_s"] = round(time.perf_counter() - started, 4)
        text = " ".join(s.text for s in segments if s.text).strip()
        return ASRResult(text, language, TASK, segments, duration, "transcribed" if text else "decoded_no_text",
                         vad_gated=True, intervals_detected=len(spans), intervals_decoded=len(spans),
                         decoder_invoked=True, runtime=runtime, detected_language=info.get("language"),
                         detected_language_probability=info.get("language_probability"))

    # --- private ----------------------------------------------------------------------------------

    def _runtime_meta(self) -> Dict[str, Any]:
        return {"backend": "faster-whisper", "device": self._choice.device if self._choice else None,
                "compute_type": self.compute_type, "degraded": self._choice.degraded if self._choice else None,
                "workers": WORKERS, "beam_size": self.beam_size}

    def _decode(self, samples: Any, language: str) -> Tuple[List[ASRSegment], Dict[str, Any]]:
        """One decoder call on exactly the samples given. Callers must have gated them."""
        options: Dict[str, Any] = {"language": language, "task": TASK, "beam_size": self.beam_size,
                                   "vad_filter": False, "condition_on_previous_text": False, "temperature": 0.0}
        try:
            return self._backend.transcribe(samples, **options)
        except Exception as exc:
            if dev.is_out_of_memory(exc):
                self.unload()
                raise RuntimeFailure("resource_exhausted", "ASR released after out-of-memory", exc) from None
            raise RuntimeFailure("inference_failed", "asr", exc) from None


def _validated_audio(samples: Any, sample_rate: int) -> Tuple[Any, float]:
    try:
        return au.validate_pcm(samples, sample_rate)
    except ValueError as exc:
        code = "unsupported_sample_rate" if "sample rate" in str(exc) else "invalid_input"
        raise RuntimeFailure(code, str(exc)) from None


def _refuse(index: int, reason: str) -> RuntimeFailure:
    return RuntimeFailure("invalid_intervals", f"interval {index}: {reason}")


def validate_speech_intervals(intervals: Any, n_samples: int) -> List[Tuple[float, float]]:
    """Validate the Silero adapter's ``(start_s, end_s)`` pairs against an audio buffer.

    The rules follow what the pinned Silero VAD can emit: seconds, start clamped at 0, end
    clamped at the audio length, at least 250 ms of speech (so never zero-length), ascending,
    and possibly touching (padding can make one end equal the next start) but never
    overlapping. The whole list is checked before any decoding; nothing is merged, padded or
    clipped. Failure messages name the interval index and rule, never audio or text.
    """
    if intervals is None:
        raise RuntimeFailure("vad_required", "speech_intervals from the VAD are required; None is refused")
    if not isinstance(intervals, (list, tuple)):
        raise RuntimeFailure("invalid_intervals", "speech_intervals must be a list of (start, end) pairs in seconds")
    duration = n_samples / au.SAMPLE_RATE
    accepted: List[Tuple[float, float]] = []
    for i, span in enumerate(intervals):
        if not isinstance(span, (list, tuple)) or len(span) != 2:
            raise _refuse(i, "must be a (start, end) pair")
        start, end = span
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (start, end)):
            raise _refuse(i, "start and end must be numbers of seconds")
        if not (math.isfinite(start) and math.isfinite(end)):
            raise _refuse(i, "non-finite value")
        if start < 0 or end < 0:
            raise _refuse(i, "negative time")
        if end < start:
            raise _refuse(i, "end before start")
        if end == start:
            raise _refuse(i, "zero-length interval (the VAD never emits one)")
        if end > duration:
            raise _refuse(i, "extends beyond the audio duration")
        if int(round(end * au.SAMPLE_RATE)) <= int(round(start * au.SAMPLE_RATE)):
            raise _refuse(i, "does not map to any audio sample")
        if accepted:
            prev_start, prev_end = accepted[-1]
            if (start, end) == (prev_start, prev_end):
                raise _refuse(i, "duplicate interval")
            if start < prev_start:
                raise _refuse(i, "intervals are not in ascending order")
            if start < prev_end:
                raise _refuse(i, "overlaps the previous interval")
        accepted.append((float(start), float(end)))
    return accepted


def _transcribe_ungated_for_benchmark(asr: WhisperASR, samples: Any, language: str) -> ASRResult:
    """PRIVATE AND BENCHMARK-ONLY. Decodes the whole buffer with no VAD gate.

    Exists only so ``ml.runtime.benchmark`` can measure Whisper's worst case on synthetic
    signals. Its result is labelled ``vad_gated=False`` and ``benchmark_only=True``. No
    application or runtime caller may use it; ``test_model_runtime`` enforces that only this
    module and the benchmark reference it.
    """
    if language not in SUPPORTED_LANGUAGES:
        raise RuntimeFailure("unsupported_language", f"language must be one of {SUPPORTED_LANGUAGES}")
    samples, duration = _validated_audio(samples, au.SAMPLE_RATE)
    if duration == 0:
        return ASRResult("", language, TASK, [], 0.0, "no_audio", vad_gated=False, intervals_detected=0,
                         intervals_decoded=0, decoder_invoked=False, benchmark_only=True, runtime=asr._runtime_meta())
    if asr._backend is None:
        raise RuntimeFailure("unavailable", "ASR is not loaded; call load() explicitly")
    started = time.perf_counter()
    try:
        segments, info = asr._decode(samples, language)
    finally:
        del samples
    runtime = asr._runtime_meta()
    runtime["latency_s"] = round(time.perf_counter() - started, 4)
    text = " ".join(s.text for s in segments if s.text).strip()
    return ASRResult(text, language, TASK, segments, duration, "transcribed" if text else "decoded_no_text",
                     vad_gated=False, intervals_detected=0, intervals_decoded=0, decoder_invoked=True,
                     benchmark_only=True, runtime=runtime, detected_language=info.get("language"),
                     detected_language_probability=info.get("language_probability"))
