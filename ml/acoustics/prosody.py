"""Prosody summary features and in-session baseline deviation. Standard library only.

This module turns measurements that were already made into prosody features:

* a per-frame F0 track in Hz, with ``None`` for unvoiced frames;
* a per-frame RMS level in dBFS;
* the VAD speech intervals;
* optionally, the ASR word count and the response latency.

It then compares one turn with the same caller's own earlier turns. ``signal.py`` makes the
measurements from samples (numpy is imported lazily there). This module does no I/O and
loads no model, so the default test suite covers it and the backend can import it.

Deviation is measured against the caller's **in-session baseline**, not against population
thresholds. Pitch and loudness vary with speaker, sex, age, phone and room, so an absolute
"high pitch" means nothing.

What this is NOT: an emotion, a distress score, a D4 value or any statement about the person.
The D4 fusion (plan step M12h) is a separate, lead-approved rule (D-8).
"""

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

PROSODY_VERSION = "prosody-1.0"

FRAME_HOP_S = 0.010
#: A gap between VAD intervals at least this long counts as a pause.
MIN_PAUSE_S = 0.25
#: Less speech than this in a turn is too little to describe (mirrors acoustics.quality).
MIN_SPEECH_S = 0.8
#: Voiced frames needed before pitch statistics are reported.
MIN_VOICED_FRAMES = 20
#: Turns that must qualify before a baseline exists (plan M12a).
BASELINE_TURNS = 2

FEATURE_NAMES: Tuple[str, ...] = (
    "f0_median_hz",
    "f0_std_st",          # pitch variability, in semitones
    "f0_range_st",        # 90th - 10th percentile pitch, in semitones
    "f0_perturbation",    # mean |dF0|/F0 between consecutive voiced frames (a jitter proxy)
    "voiced_ratio",       # voiced frames / speech frames
    "rms_mean_db",
    "rms_std_db",
    "pause_ratio",        # silence share of the turn span
    "pause_count",
    "mean_pause_s",
    "max_pause_s",
    "speech_rate_wps",    # ASR words per second of speech; None without a transcript
    "response_latency_s", # None when turn timing is unknown
)

#: Features compared against the baseline, with the smallest spread (in the feature's unit)
#: used as the denominator, so a very steady baseline cannot make tiny changes look huge.
DEVIATION_FLOORS: Dict[str, float] = {
    "f0_median_st": 1.0,      # median pitch expressed in semitones for comparison
    "f0_std_st": 0.5,
    "f0_range_st": 1.0,
    "rms_mean_db": 3.0,
    "pause_ratio": 0.10,
    "speech_rate_wps": 0.5,
}

UNAVAILABLE = "unavailable"


def _semitones(hz: float, ref_hz: float = 100.0) -> float:
    return 12.0 * math.log2(hz / ref_hz)


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile of an already sorted, non-empty sequence."""
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    frac = pos - lo
    return float(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def validate_intervals(intervals: Sequence[Sequence[float]], duration_s: float) -> List[Tuple[float, float]]:
    """Return VAD intervals as sorted float pairs; refuse malformed input with a fixed message."""
    out: List[Tuple[float, float]] = []
    prev_end = 0.0
    for item in intervals:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("speech intervals must be (start_s, end_s) pairs")
        start, end = item
        if isinstance(start, bool) or isinstance(end, bool):
            raise ValueError("speech interval bounds must be numbers")
        start, end = float(start), float(end)
        if not (math.isfinite(start) and math.isfinite(end)) or start < 0 or end <= start:
            raise ValueError("speech intervals must be finite, non-negative and non-empty")
        if end > duration_s + 1e-6:
            raise ValueError("speech interval ends after the audio")
        if start < prev_end - 1e-9:
            raise ValueError("speech intervals must be ascending and non-overlapping")
        out.append((start, end))
        prev_end = end
    return out


def pause_features(intervals: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    """Pauses inside the turn: between the first speech onset and the last speech offset.

    Leading and trailing silence is excluded: it reflects when the recording started and
    stopped, not how the person spoke.
    """
    if not intervals:
        return {"speech_s": 0.0, "span_s": 0.0, "pause_ratio": None, "pause_count": 0,
                "mean_pause_s": None, "max_pause_s": None}
    speech = sum(e - s for s, e in intervals)
    span = intervals[-1][1] - intervals[0][0]
    gaps = [b[0] - a[1] for a, b in zip(intervals, intervals[1:])]
    pauses = [g for g in gaps if g >= MIN_PAUSE_S]
    return {
        "speech_s": round(speech, 4),
        "span_s": round(span, 4),
        "pause_ratio": round(max(0.0, span - speech) / span, 4) if span > 0 else 0.0,
        "pause_count": len(pauses),
        "mean_pause_s": round(_mean(pauses), 4) if pauses else 0.0,
        "max_pause_s": round(max(pauses), 4) if pauses else 0.0,
    }


def summarize_turn(
    f0_hz: Sequence[Optional[float]],
    rms_db: Sequence[float],
    intervals: Sequence[Sequence[float]],
    duration_s: float,
    *,
    word_count: Optional[int] = None,
    response_latency_s: Optional[float] = None,
    hop_s: float = FRAME_HOP_S,
) -> Dict[str, Any]:
    """Summarise one turn's prosody.

    ``f0_hz`` and ``rms_db`` are frame tracks with a hop of ``hop_s``. Only frames inside the
    speech intervals count. A feature that cannot be measured is ``None``, never zero.
    """
    if len(f0_hz) != len(rms_db):
        raise ValueError("f0 and rms tracks must have the same number of frames")
    ivals = validate_intervals(intervals, duration_s)
    pauses = pause_features(ivals)

    in_speech: List[int] = []
    for s, e in ivals:
        first = int(math.floor(s / hop_s))
        last = min(len(rms_db), int(math.ceil(e / hop_s)))
        in_speech.extend(range(max(0, first), last))
    in_speech = sorted(set(in_speech))

    voiced = [f0_hz[i] for i in in_speech if f0_hz[i] is not None and f0_hz[i] > 0]
    levels = [float(rms_db[i]) for i in in_speech]

    features: Dict[str, Any] = {name: None for name in FEATURE_NAMES}
    reasons: List[str] = []

    if pauses["speech_s"] < MIN_SPEECH_S:
        reasons.append("insufficient_speech")
    features["pause_ratio"] = pauses["pause_ratio"]
    features["pause_count"] = pauses["pause_count"]
    features["mean_pause_s"] = pauses["mean_pause_s"]
    features["max_pause_s"] = pauses["max_pause_s"]

    if levels:
        features["rms_mean_db"] = round(_mean(levels), 3)
        features["rms_std_db"] = round(_std(levels), 3)
    if in_speech:
        features["voiced_ratio"] = round(len(voiced) / len(in_speech), 4)

    if len(voiced) >= MIN_VOICED_FRAMES:
        st = sorted(_semitones(v) for v in voiced)
        features["f0_median_hz"] = round(_percentile(sorted(voiced), 0.5), 2)
        features["f0_std_st"] = round(_std(st), 4)
        features["f0_range_st"] = round(_percentile(st, 0.9) - _percentile(st, 0.1), 4)
        steps = []
        prev = None
        for i in in_speech:
            cur = f0_hz[i]
            if cur is not None and cur > 0 and prev is not None and prev > 0:
                steps.append(abs(cur - prev) / prev)
            prev = cur
        features["f0_perturbation"] = round(_mean(steps), 5) if steps else None
    else:
        reasons.append("too_few_voiced_frames")

    if word_count is not None and pauses["speech_s"] > 0:
        if word_count < 0:
            raise ValueError("word count cannot be negative")
        features["speech_rate_wps"] = round(word_count / pauses["speech_s"], 4)
    if response_latency_s is not None:
        if response_latency_s < 0 or not math.isfinite(response_latency_s):
            raise ValueError("response latency must be finite and non-negative")
        features["response_latency_s"] = round(float(response_latency_s), 4)

    return {
        "version": PROSODY_VERSION,
        "features": features,
        "speech_s": pauses["speech_s"],
        "qualifies_for_baseline": not reasons,
        "reasons": reasons,
    }


def _comparable(features: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    f0 = features.get("f0_median_hz")
    return {
        "f0_median_st": _semitones(f0) if f0 else None,
        "f0_std_st": features.get("f0_std_st"),
        "f0_range_st": features.get("f0_range_st"),
        "rms_mean_db": features.get("rms_mean_db"),
        "pause_ratio": features.get("pause_ratio"),
        "speech_rate_wps": features.get("speech_rate_wps"),
    }


def baseline(turn_summaries: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build the caller's baseline from their earliest qualifying turns.

    Returns ``{"status": "ready"|"unavailable", "turns_used", "stats"}``. ``stats`` maps each
    compared feature to ``{"mean", "spread"}``. The spread is at least the feature's floor, and
    exactly the floor when only one value exists.
    """
    used = [t for t in turn_summaries if t.get("qualifies_for_baseline")][:BASELINE_TURNS]
    if len(used) < BASELINE_TURNS:
        return {"status": UNAVAILABLE, "turns_used": len(used), "stats": {}}
    stats: Dict[str, Dict[str, float]] = {}
    for name, floor in DEVIATION_FLOORS.items():
        values = [v for v in (_comparable(t["features"])[name] for t in used) if v is not None]
        if not values:
            continue
        stats[name] = {"mean": round(_mean(values), 5), "spread": round(max(_std(values), floor), 5)}
    return {"status": "ready", "turns_used": len(used), "stats": stats}


def deviation(turn_summary: Mapping[str, Any], base: Mapping[str, Any]) -> Dict[str, Any]:
    """Signed deviation of one turn from the baseline, in baseline-spread units.

    Positive means higher than this caller's own baseline: higher pitch, wider range,
    louder, more pausing, faster. No direction is labelled good or bad here.
    """
    if base.get("status") != "ready":
        return {"status": UNAVAILABLE, "reason": "no_baseline", "deviations": {}}
    if not turn_summary.get("qualifies_for_baseline"):
        return {"status": UNAVAILABLE, "reason": "turn_not_measurable",
                "deviations": {}, "turn_reasons": list(turn_summary.get("reasons") or [])}
    current = _comparable(turn_summary["features"])
    out: Dict[str, float] = {}
    for name, stat in base["stats"].items():
        value = current.get(name)
        if value is None:
            continue
        out[name] = round((value - stat["mean"]) / stat["spread"], 4)
    return {"status": "ready" if out else UNAVAILABLE, "reason": None if out else "no_comparable_features",
            "deviations": out}
