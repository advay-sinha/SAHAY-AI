"""Audio validation and synthetic test signals. Standard library only.

Signals generated here are for **functional** checks: they prove the runtime loads, accepts
input and returns well-formed output. They contain no speech and say nothing about
recognition or detection quality. Nothing here reads, writes or retains audio.
"""

import importlib
import math
import random
from array import array
from typing import Any, Sequence, Tuple

SAMPLE_RATE = 16000


def validate_pcm(audio: Any, sample_rate: int) -> Tuple[Any, float]:
    """Accept 16 kHz mono float PCM; return ``(audio, duration_seconds)``.

    Raises ``ValueError`` with a fixed message; the audio itself is never echoed.
    """
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"unsupported sample rate: exactly {SAMPLE_RATE} Hz mono is required")
    ndim = getattr(audio, "ndim", 1)
    if ndim != 1:
        raise ValueError("audio must be mono (one-dimensional)")
    if isinstance(audio, (str, bytes, bytearray)):
        raise ValueError("audio must be float samples, not bytes or text")
    try:
        n = len(audio)
    except TypeError:
        raise ValueError("audio must be a sequence of float samples") from None
    return audio, n / SAMPLE_RATE


def silence(seconds: float) -> array:
    return array("f", bytes(4 * int(seconds * SAMPLE_RATE)))


def tone(seconds: float, freq: float = 440.0, amplitude: float = 0.3) -> array:
    n = int(seconds * SAMPLE_RATE)
    return array("f", (amplitude * math.sin(2 * math.pi * freq * i / SAMPLE_RATE) for i in range(n)))


def voiced_pattern(seconds: float, seed: int = 7, amplitude: float = 0.3) -> array:
    """A deterministic speech-like signal: harmonic pulses with a syllable-rate envelope.

    It imitates the energy rhythm of voiced sound so the VAD and ASR paths are exercised;
    it is not speech and carries no words.
    """
    rng = random.Random(seed)
    n = int(seconds * SAMPLE_RATE)
    f0 = 140.0
    out = array("f")
    for i in range(n):
        t = i / SAMPLE_RATE
        envelope = max(0.0, math.sin(2 * math.pi * 3.5 * t)) ** 2
        f = f0 * (1 + 0.08 * math.sin(2 * math.pi * 0.7 * t))
        s = sum(math.sin(2 * math.pi * f * k * t) / k for k in (1, 2, 3, 4, 5))
        out.append(amplitude * envelope * (0.6 * s / 2.3 + 0.02 * rng.uniform(-1, 1)))
    return out


def concat(*parts: Sequence[float]) -> array:
    out = array("f")
    for p in parts:
        out.extend(p)
    return out


def to_float32_numpy(audio: Any) -> Any:
    """Convert to a contiguous float32 NumPy array (NumPy imported only here, only when called)."""
    np = importlib.import_module("numpy")
    return np.ascontiguousarray(np.asarray(audio, dtype=np.float32))
