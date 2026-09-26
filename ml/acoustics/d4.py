"""D4 (acute distress) from voice: in-session prosodic deviation. Standard library only.

Plan step M12h, decisions D-4 (EXT-121) and D-8. Pure: measurements in, a dimension record out.

Rule (deterministic, conservative, interpretable):
* The caller's first ``prosody.BASELINE_TURNS`` usable voice turns form their own baseline.
  Pitch, loudness and pausing vary by speaker, sex and phone, so only deviation from the same
  person counts, never an absolute "high pitch".
* Each later usable turn is scored from the upward deviations (in baseline-spread units) of:
  median pitch, pitch variability, loudness and pause ratio. Raised, more variable, louder or
  more hesitant speech than the caller's own start is the acoustic pattern associated with acute
  arousal. Downward deviations add nothing: a flatter voice is not read as calm or as low mood.
* D4 is the highest turn score, 0-100. Confidence is capped at ``MAX_CONFIDENCE`` because this
  is weak, uncalibrated evidence; the SVI weights are provisional too.
* Fewer than ``MIN_VOICE_TURNS`` usable turns -> D4 is unavailable ("not measured"), and on an
  audio channel the assessment keeps abstaining (PC-08).

Speech-emotion (SER) input is supported but OFF (``SER_ENABLED = False``). Under D-8 it may
contribute at most ``SER_MAX_SHARE`` of D4, and only after the promotion gate passes on team
recordings (R7). Nothing here reads text, diagnoses, or labels the person.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import prosody

D4_VERSION = "d4-prosody-1.0"
MIN_VOICE_TURNS = prosody.BASELINE_TURNS + 1
MAX_CONFIDENCE = 0.6
BASE_CONFIDENCE = 0.4
CONFIDENCE_PER_TURN = 0.05
#: Points per baseline-spread unit of the combined upward deviation (2 units -> 50, 4 -> 100).
POINTS_PER_UNIT = 25.0
#: Combination weights over upward deviations (sum 1.0).
WEIGHTS = {"f0_median_st": 0.35, "f0_std_st": 0.20, "rms_mean_db": 0.20, "pause_ratio": 0.25}
#: D-8: speech emotion may contribute at most this share of D4, and only once enabled.
SER_MAX_SHARE = 0.30
SER_ENABLED = False
SER_DISTRESS_CLASSES = ("fearful", "angry", "sad")
#: SAFE-SIGNAL (AE-12): text severity and D4 differing by more than this -> verification card.
DIVERGENCE_POINTS = 40.0


def _summary(voice_turn: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The prosody summary stored for a voice turn, or None when absent or poor audio."""
    asr = voice_turn.get("asr") or {}
    features = asr.get("prosody")
    if not isinstance(features, Mapping) or asr.get("poor_audio") or asr.get("low_asr_confidence"):
        return None
    reasons = list(asr.get("prosody_reasons") or [])
    return {"features": dict(features), "reasons": reasons, "qualifies_for_baseline": not reasons}


def turn_score(deviations: Mapping[str, float]) -> float:
    combined = sum(w * max(0.0, float(deviations.get(k, 0.0))) for k, w in WEIGHTS.items())
    return round(min(100.0, POINTS_PER_UNIT * combined), 2)


def ser_distress(probabilities: Mapping[str, float]) -> float:
    """0-100 from SER class probabilities (fearful + angry + sad)."""
    return round(100.0 * min(1.0, sum(float(probabilities.get(c, 0.0)) for c in SER_DISTRESS_CLASSES)), 2)


def fuse(prosody_score: float, ser_score: Optional[float], enabled: bool = SER_ENABLED) -> float:
    """D-8 cap: SER never exceeds SER_MAX_SHARE of D4, and contributes nothing while disabled."""
    if not enabled or ser_score is None:
        return prosody_score
    return round((1.0 - SER_MAX_SHARE) * prosody_score + SER_MAX_SHARE * ser_score, 2)


def score_d4(voice_turns: Sequence[Mapping[str, Any]], *, ser_enabled: bool = SER_ENABLED) -> Dict[str, Any]:
    """D4 dimension record from the victim's voice turns, in order.

    Each voice turn is a victim turn dict carrying ``asr`` (prosody features, prosody_reasons,
    poor_audio, low_asr_confidence, optional ``ser`` probabilities).
    """
    usable = [(t, s) for t in voice_turns for s in [_summary(t)] if s is not None and s["qualifies_for_baseline"]]
    base = prosody.baseline([s for _, s in usable])
    if len(usable) < MIN_VOICE_TURNS or base["status"] != "ready":
        return {"dimension": "D4", "score": None, "confidence": None, "evidence_turn_ids": [],
                "basis": "unavailable", "reason": "insufficient_usable_voice_turns",
                "usable_voice_turns": len(usable), "version": D4_VERSION}
    per_turn: List[Dict[str, Any]] = []
    for turn, summary in usable[prosody.BASELINE_TURNS:]:
        dev = prosody.deviation(summary, base)
        if dev["status"] != "ready":
            continue
        p_score = turn_score(dev["deviations"])
        ser = (turn.get("asr") or {}).get("ser")
        s_score = ser_distress(ser) if isinstance(ser, Mapping) else None
        per_turn.append({"turn_id": str(turn["id"]), "prosody": p_score, "ser": s_score,
                         "score": fuse(p_score, s_score, ser_enabled), "deviations": dev["deviations"]})
    if not per_turn:
        return {"dimension": "D4", "score": None, "confidence": None, "evidence_turn_ids": [],
                "basis": "unavailable", "reason": "no_comparable_voice_turn",
                "usable_voice_turns": len(usable), "version": D4_VERSION}
    top = max(per_turn, key=lambda r: r["score"])
    evidence = [r["turn_id"] for r in per_turn if r["score"] > 0 and r["score"] >= 0.5 * top["score"]]
    confidence = min(MAX_CONFIDENCE, BASE_CONFIDENCE + CONFIDENCE_PER_TURN * len(per_turn))
    return {
        "dimension": "D4", "score": top["score"], "confidence": round(confidence, 4),
        "evidence_turn_ids": evidence if top["score"] > 0 else [],
        "basis": "prosody_deviation" + ("+ser" if ser_enabled else ""),
        "ser_enabled": ser_enabled, "usable_voice_turns": len(usable), "compared_turns": len(per_turn),
        "turn_scores": [{k: r[k] for k in ("turn_id", "prosody", "ser", "score")} for r in per_turn],
        "version": D4_VERSION,
    }


def safe_signal(d4_score: Optional[float], text_severity: Optional[float]) -> Optional[Dict[str, Any]]:
    """SAFE-SIGNAL (AE-12): a neutral verification prompt when voice and words disagree.

    Never an alert and never a band change: it asks the officer to check, nothing more.
    """
    if d4_score is None or text_severity is None:
        return None
    gap = round(float(d4_score) - float(text_severity), 2)
    if abs(gap) <= DIVERGENCE_POINTS:
        return None
    return {
        "divergence": abs(gap),
        "direction": "voice_more_distressed_than_words" if gap > 0 else "words_more_severe_than_voice",
        "text_severity": round(float(text_severity), 2), "d4": round(float(d4_score), 2),
        "prompt": "Voice and words point in different directions. Please verify with the caller.",
    }
