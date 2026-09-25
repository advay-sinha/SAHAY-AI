"""Frame-level pitch, energy and audio-quality measurement from 16 kHz mono samples.

numpy is imported only when a function runs (EXT-121), so importing this module needs no
third-party package and the default test suite stays dependency-free. The output feeds
``prosody.summarize_turn`` and ``quality.is_poor``.

Pitch uses YIN (de Cheveigné and Kawahara, 2002): a cumulative-mean-normalised difference
function with an absolute threshold and parabolic refinement, vectorised across frames.
A frame counts as voiced only if it clears both the YIN threshold and an energy floor.

Nothing here decides anything about the person. Audio is never logged or written.
"""

import importlib
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

SAMPLE_RATE = 16000
HOP = 160                 # 10 ms, the same hop as prosody.FRAME_HOP_S
RMS_WINDOW = 400          # 25 ms
YIN_WINDOW = 512          # 32 ms integration window
FMIN_HZ = 65.0
FMAX_HZ = 500.0
YIN_THRESHOLD = 0.15
VOICING_FLOOR_DB = -50.0  # frames quieter than this are never voiced
CLIP_LEVEL = 0.99
MIN_NOISE_FRAMES = 10


def _np() -> Any:
    return importlib.import_module("numpy")


def _as_array(samples: Any) -> Any:
    np = _np()
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError("audio must be mono (one-dimensional)")
    if x.size == 0:
        raise ValueError("audio is empty")
    if not np.all(np.isfinite(x)):
        raise ValueError("audio contains non-finite samples")
    return x


def frame_count(n_samples: int) -> int:
    return int(math.ceil(n_samples / HOP))


def rms_db(samples: Any) -> List[float]:
    """Per-frame RMS level in dBFS (25 ms window, 10 ms hop)."""
    np = _np()
    x = _as_array(samples)
    n = frame_count(x.size)
    padded = np.concatenate([x, np.zeros(RMS_WINDOW)])
    idx = np.arange(n)[:, None] * HOP + np.arange(RMS_WINDOW)[None, :]
    frames = padded[idx]
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    return [float(v) for v in 20.0 * np.log10(rms + 1e-10)]


def yin_f0(samples: Any, *, fmin: float = FMIN_HZ, fmax: float = FMAX_HZ,
           threshold: float = YIN_THRESHOLD, levels_db: Optional[Sequence[float]] = None) -> List[Optional[float]]:
    """Per-frame F0 in Hz (10 ms hop); ``None`` where the frame is unvoiced or too quiet."""
    np = _np()
    x = _as_array(samples)
    if not (0 < fmin < fmax < SAMPLE_RATE / 2):
        raise ValueError("pitch range must satisfy 0 < fmin < fmax < Nyquist")
    tau_min = int(math.floor(SAMPLE_RATE / fmax))
    tau_max = int(math.ceil(SAMPLE_RATE / fmin))
    w = YIN_WINDOW
    span = w + tau_max
    n = frame_count(x.size)
    padded = np.concatenate([x, np.zeros(span)])
    frames = padded[np.arange(n)[:, None] * HOP + np.arange(span)[None, :]]

    # Difference function d(tau) = e0 + e_tau - 2 * r(tau), with r computed by FFT.
    size = 1 << int(math.ceil(math.log2(span + w)))
    spec_full = np.fft.rfft(frames, size, axis=1)
    spec_head = np.fft.rfft(frames[:, :w], size, axis=1)
    corr = np.fft.irfft(np.conj(spec_head) * spec_full, size, axis=1)[:, :tau_max + 1]
    sq = np.concatenate([np.zeros((n, 1)), np.cumsum(frames * frames, axis=1)], axis=1)
    taus = np.arange(tau_max + 1)
    e_tau = sq[:, taus + w] - sq[:, taus]
    e0 = e_tau[:, :1]
    d = np.maximum(e0 + e_tau - 2.0 * corr, 0.0)

    # Cumulative mean normalised difference.
    cmnd = np.ones_like(d)
    running = np.cumsum(d[:, 1:], axis=1)
    cmnd[:, 1:] = d[:, 1:] * np.arange(1, tau_max + 1)[None, :] / np.maximum(running, 1e-12)

    region = cmnd[:, tau_min:tau_max]
    below = region < threshold
    has = below.any(axis=1)
    first = np.argmax(below, axis=1)
    # Walk from the first sub-threshold lag down to its local minimum.
    rising = np.concatenate([region[:, 1:] >= region[:, :-1], np.ones((n, 1), dtype=bool)], axis=1)
    cols = np.arange(region.shape[1])[None, :]
    local = np.argmax(rising & (cols >= first[:, None]), axis=1)

    if levels_db is None:
        levels_db = rms_db(x)
    levels = np.asarray(levels_db, dtype=np.float64)
    if levels.shape[0] != n:
        raise ValueError("levels must have one value per frame")

    out: List[Optional[float]] = []
    for i in range(n):
        if not has[i] or levels[i] < VOICING_FLOOR_DB:
            out.append(None)
            continue
        k = int(local[i])
        tau = float(k + tau_min)
        if 0 < k < region.shape[1] - 1:
            a, b, c = region[i, k - 1], region[i, k], region[i, k + 1]
            den = a - 2.0 * b + c
            if abs(den) > 1e-12:
                tau += 0.5 * (a - c) / den
        out.append(float(SAMPLE_RATE / tau) if tau > 0 else None)
    return out


def _speech_mask(n_frames: int, intervals: Sequence[Tuple[float, float]]) -> List[bool]:
    hop_s = HOP / SAMPLE_RATE
    mask = [False] * n_frames
    for s, e in intervals:
        for i in range(max(0, int(math.floor(s / hop_s))), min(n_frames, int(math.ceil(e / hop_s)))):
            mask[i] = True
    return mask


def quality(samples: Any, intervals: Sequence[Tuple[float, float]],
            levels_db: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    """Audio-quality metrics for ``acoustics.quality.is_poor``.

    SNR is the speech level minus the median level of non-speech frames. When the turn has
    fewer than ``MIN_NOISE_FRAMES`` non-speech frames, the noise floor is estimated from the
    10th percentile of the speech frames and ``snr_method`` says so.
    """
    np = _np()
    x = _as_array(samples)
    levels = np.asarray(levels_db if levels_db is not None else rms_db(x), dtype=np.float64)
    mask = np.asarray(_speech_mask(levels.shape[0], intervals))
    speech_ms = 1000.0 * sum(e - s for s, e in intervals)
    clipping = float(np.mean(np.abs(x) >= CLIP_LEVEL))
    if not mask.any():
        return {"snr_db": None, "snr_method": "no_speech", "speech_ms": 0.0, "clipping_ratio": round(clipping, 5)}
    speech_power = np.mean(10.0 ** (levels[mask] / 10.0))
    speech_db = 10.0 * math.log10(max(float(speech_power), 1e-20))
    noise = levels[~mask]
    if noise.shape[0] >= MIN_NOISE_FRAMES:
        noise_db, method = float(np.median(noise)), "non_speech_frames"
    else:
        noise_db, method = float(np.percentile(levels[mask], 10)), "speech_percentile_estimate"
    return {"snr_db": round(speech_db - noise_db, 3), "snr_method": method,
            "speech_ms": round(speech_ms, 1), "clipping_ratio": round(clipping, 5)}


def measure(samples: Any, intervals: Sequence[Tuple[float, float]], *,
            sample_rate: int = SAMPLE_RATE) -> Dict[str, Any]:
    """Tracks and quality for one turn: the input to ``prosody.summarize_turn``."""
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"unsupported sample rate: exactly {SAMPLE_RATE} Hz mono is required")
    x = _as_array(samples)
    levels = rms_db(x)
    return {
        "f0_hz": yin_f0(x, levels_db=levels),
        "rms_db": levels,
        "duration_s": x.size / SAMPLE_RATE,
        "quality": quality(x, intervals, levels),
    }
