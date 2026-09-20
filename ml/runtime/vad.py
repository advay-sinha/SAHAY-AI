"""Lazy Silero VAD adapter (official ``silero-vad`` package, pinned in the manifest).

It returns speech intervals and nothing else: speech presence, not distress, emotion or D4.
The model is the TorchScript file bundled inside the pinned wheel; it is loaded from the
package, never through Torch Hub, and never over the network. Audio is processed in memory
and not retained. The package's default detection settings are used unchanged.
"""

import importlib
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

from . import audio as au, device as dev
from .offline import apply_offline_env
from .status import AVAILABLE, LOADED, UNAVAILABLE, RuntimeFailure, RuntimeStatus

LOGICAL_ID = "silero_vad"
FUNCTIONAL_ONLY = "functional runtime check on synthetic signals; not a detection-accuracy measurement"


@dataclass
class VADResult:
    intervals: List[Tuple[float, float]]
    duration_s: float
    speech_s: float
    sample_rate: int = au.SAMPLE_RATE
    model: str = LOGICAL_ID


class SileroBackend:
    def __init__(self) -> None:
        apply_offline_env()
        self.torch = dev.import_torch()
        silero = importlib.import_module("silero_vad")
        self._get = silero.get_speech_timestamps
        self.model = silero.load_silero_vad(onnx=False)  # bundled file; no Torch Hub

    def speech_timestamps(self, samples: Any) -> List[Tuple[float, float]]:
        wav = self.torch.from_numpy(au.to_float32_numpy(samples))
        stamps = self._get(wav, self.model, sampling_rate=au.SAMPLE_RATE, return_seconds=True)
        return [(float(s["start"]), float(s["end"])) for s in stamps]

    def close(self) -> None:
        self.model = None


class SileroVAD:
    def __init__(self, backend_factory: Optional[Callable[[], Any]] = None) -> None:
        self._factory = backend_factory or SileroBackend
        self._backend: Any = None

    def status(self) -> RuntimeStatus:
        if self._backend is not None:
            return RuntimeStatus(LOGICAL_ID, LOADED, "voice_activity_detection", "cpu", "float32")
        if self._factory is SileroBackend and not (dev.package_available("silero_vad")
                                                    and dev.package_available("torch")):
            return RuntimeStatus(LOGICAL_ID, UNAVAILABLE, "silero-vad is not installed in this environment")
        return RuntimeStatus(LOGICAL_ID, AVAILABLE, "voice_activity_detection")

    def load(self) -> RuntimeStatus:
        if self._backend is None:
            state = self.status()
            if state.state != AVAILABLE:
                raise RuntimeFailure("unavailable", state.reason)
            try:
                self._backend = self._factory()
            except Exception as exc:
                raise RuntimeFailure("load_failed", "silero vad", exc) from None
        return self.status()

    def unload(self) -> None:
        backend, self._backend = self._backend, None
        if backend is not None:
            backend.close()
        dev.release()

    def intervals(self, samples: Any, sample_rate: int = au.SAMPLE_RATE) -> VADResult:
        if self._backend is None:
            raise RuntimeFailure("unavailable", "VAD is not loaded; call load() explicitly")
        try:
            samples, duration = au.validate_pcm(samples, sample_rate)
        except ValueError as exc:
            code = "unsupported_sample_rate" if "sample rate" in str(exc) else "invalid_input"
            raise RuntimeFailure(code, str(exc)) from None
        if duration == 0:
            return VADResult([], 0.0, 0.0)
        try:
            spans = self._backend.speech_timestamps(samples)
        except Exception as exc:
            raise RuntimeFailure("inference_failed", "vad", exc) from None
        return VADResult(spans, duration, round(sum(e - s for s, e in spans), 3))
