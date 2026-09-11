"""Deterministic text assessment pipeline.

Pure: standard library only, no I/O, no model. Turns in, assessment out, and
the same turns always give the same assessment.

    assess(turns, consent_granted, crisis_fired=False, *, channel) -> {
        suppressed, dims, svi, band, needs_human, overrides_applied,
        abstention_reasons, aggregate_confidence, structured, alerts,
        recommendations, uncertainty, cause, normalization
    }

What it does NOT do: diagnose, characterise the person, contact anyone, or
produce a score it cannot support.

Acoustic distress (D4), PC-08 (lead decision 2026-09-11):
  * typed channels (mobile_chat, portal_chat): D4 has no measurement path. It
    is declared STRUCTURALLY unavailable, reported as unavailable (never zero)
    and the SVI is renormalised over the other eight weights (denominator 0.88);
  * audio channels (mobile_voice, upload): D4 should be measured. No acoustic
    model runs in this build, so D4 is missing at runtime. That is NOT
    rescaled: the assessment abstains (Needs Human Assessment).

Nothing here is clinically validated.
"""

from typing import Any, Dict, List, Mapping, Sequence

from .guardrails import crisis_check
from .nlp import langid
from .nlp.detectors import TEXT_DIMENSIONS, match_turn, score_crisis, score_dimension, unavailable
from .nlp.extraction import conflicting_safety, extract
from .nlp.recommend import recommend
from .svi import compute
from .svi.dimensions import DIMENSION_ORDER

PIPELINE_VERSION = "text-lexicon-v1"

#: Channels (CONTRACTS.md section 8) on which acoustic distress cannot exist.
#: Mirrors backend/app/core/enums.py TEXT_CHANNELS (test_contract_mirror).
TEXT_CHANNELS = ("mobile_chat", "portal_chat")
AUDIO_CHANNELS = ("mobile_voice", "upload")

#: Fewer letters than this across all victim turns is too little to assess.
MIN_TOTAL_LETTERS = 20

_COERCION_TERMS = ("withdraw", "take back", "not to complain", "wapas", "वापस")


def _victim(turns: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [t for t in turns if t.get("speaker") == "victim" and str(t.get("text", "")).strip()]


def _alerts(dims: Mapping[str, Mapping[str, Any]],
            victim: Sequence[Mapping[str, Any]] = ()) -> List[Dict[str, Any]]:
    def d(k):
        return dims.get(k) or {}

    out: List[Dict[str, Any]] = []

    if d("D2").get("evidence_turn_ids"):
        out.append({"type": "crisis", "severity": "critical",
                    "evidence_turn_ids": d("D2")["evidence_turn_ids"]})

    d1 = d("D1").get("score") or 0.0
    d3 = d("D3").get("score") or 0.0
    threat_ev = list(d("D1").get("evidence_turn_ids") or []) + list(d("D3").get("evidence_turn_ids") or [])
    if d1 >= 70:
        out.append({"type": "threat", "severity": "critical", "evidence_turn_ids": sorted(set(threat_ev))})
    elif d3 >= 80 or d1 >= 60:
        out.append({"type": "threat", "severity": "high", "evidence_turn_ids": sorted(set(threat_ev))})

    d7 = d("D7").get("score") or 0.0
    if d7 >= 85:
        out.append({"type": "medical", "severity": "critical", "evidence_turn_ids": d("D7")["evidence_turn_ids"]})
    elif d7 >= 65:
        out.append({"type": "medical", "severity": "high", "evidence_turn_ids": d("D7")["evidence_turn_ids"]})

    coercion_terms = [t for t in d("D3").get("matched_terms") or [] if any(c in t for c in _COERCION_TERMS)]
    d9 = d("D9").get("score") or 0.0
    coercion_ev = list(d("D9").get("evidence_turn_ids") or [])
    if coercion_terms:
        # Cite only the victim turns whose OWN D3 match is a coercion term (for
        # example "withdraw the complaint"), not every D3 turn. The firing
        # condition is unchanged; only the evidence is more precise. If no
        # turn can be attributed (not expected), keep all D3 evidence rather
        # than drop any.
        own = [str(t["id"]) for t in victim
               if any(any(c in term for c in _COERCION_TERMS)
                      for term in (match_turn("D3", str(t.get("text", ""))) or (0, []))[1])]
        coercion_ev += own or list(d("D3").get("evidence_turn_ids") or [])
    if d9 >= 65 or coercion_terms:
        out.append({"type": "coercion", "severity": "high", "evidence_turn_ids": sorted(set(coercion_ev))})
    return out


def assess(
    turns: Sequence[Mapping[str, Any]],
    consent_granted: bool,
    crisis_fired: bool = False,
    *,
    channel: str,
) -> Dict[str, Any]:
    """Assess a conversation so far. `turns` items: id, speaker, text, state."""
    if channel not in TEXT_CHANNELS + AUDIO_CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    text_channel = channel in TEXT_CHANNELS
    victim = _victim(turns)

    if not consent_granted:
        # Consent declined: no analysis at all. Not a low score — no score.
        return {
            "suppressed": True, "dims": {}, "svi": None, "band": None, "needs_human": True,
            "overrides_applied": [], "abstention_reasons": ["consent_declined"],
            "aggregate_confidence": 0.0, "structured": None, "alerts": [], "recommendations": [],
            "uncertainty": {"reason": "consent declined — assessment suppressed"},
            "cause": "abstain:consent_declined", "pipeline_version": PIPELINE_VERSION,
            "normalization": {},
        }

    dims: Dict[str, Dict[str, Any]] = {}
    for dim in TEXT_DIMENSIONS:
        dims[dim] = score_dimension(dim, victim)
    dims["D2"] = score_crisis(victim, crisis_check)
    if text_channel:
        dims["D4"] = unavailable("D4", "structurally_unavailable_on_text_channel")
    else:
        dims["D4"] = unavailable("D4", "acoustic_model_not_running")

    structured = extract(victim)
    language = langid.aggregate(str(t["text"]) for t in victim)
    letters = sum(ch.isalpha() for t in victim for ch in str(t["text"]))

    # Imminent danger stated in answer to the licensed safety question (S2).
    immediate = any(
        t.get("state") == "S2" and t["id"] in (dims["D1"].get("evidence_turn_ids") or [])
        and (dims["D1"].get("score") or 0) >= 85
        for t in victim
    )
    crisis = crisis_fired or bool(dims["D2"].get("evidence_turn_ids"))

    quality = {
        "low_language_confidence": bool(language["low"]),
        "poor_input_quality": letters < MIN_TOTAL_LETTERS,
        "conflicting_evidence": conflicting_safety(structured),
        "crisis_interrupt_fired": crisis,
        "immediate_danger_confirmed": immediate,
        # Audio channel with no acoustic measurement: abstain, never rescale.
        "acoustic_not_measured": not text_channel,
    }

    scores = {k: v["score"] for k, v in dims.items() if v.get("score") is not None}
    confs = {k: v["confidence"] for k, v in dims.items() if v.get("confidence") is not None}
    result = compute(scores, confs, {**quality, "structurally_unavailable": ["D4"] if text_channel else []})
    normalization = {
        "scoring_version": result["scoring_version"],
        "channel": channel,
        "available_dimensions": result["available_dimensions"],
        "structurally_unavailable": result["structurally_unavailable"],
        "weight_denominator": result["weight_denominator"],
        "normalization_factor": result["normalization_factor"],
    }

    if result["overrides_applied"]:
        cause = "override:" + ",".join(result["overrides_applied"])
    elif result["needs_human"]:
        cause = "abstain:" + ",".join(result["abstention_reasons"] or ["needs_human"])
    else:
        cause = "weighted_sum"

    # Safety alerts fire on evidence alone: a threat stated in turn two must not
    # wait for the aggregate confidence to recover.
    alerts = _alerts(dims, victim)
    # Pathway suggestions draw on the assessment, so they are withheld while
    # the system itself says it cannot assess -- except emergency support in a
    # crisis, which must never wait.
    # (The engine also sets needs_human on a hard override that forces
    # Critical; that case has a band and keeps its suggestions. Only true
    # abstention -- no band at all -- withholds them.)
    recs = recommend(dims, result["band"], crisis)
    if result["band"] is None and not crisis:
        recs = []

    return {
        "suppressed": False,
        "dims": {d: dims[d] for d in DIMENSION_ORDER},
        "svi": result["svi"],
        "band": result["band"],
        "needs_human": result["needs_human"],
        "overrides_applied": result["overrides_applied"],
        "abstention_reasons": result["abstention_reasons"],
        "aggregate_confidence": result["aggregate_confidence"],
        "breakdown": result["breakdown"],
        "structured": structured,
        "alerts": alerts,
        "recommendations": recs,
        "uncertainty": {
            "aggregate_confidence": result["aggregate_confidence"],
            "language": language["lang"],
            "language_confidence": language["confidence"],
            "acoustic": ("structurally unavailable — typed channel; D4 excluded and weights "
                         "renormalised (not measured, not zero)") if text_channel
                        else "not measured — no acoustic model in this build; assessment abstains",
            "asr_confidence": "not applicable — typed text" if text_channel else "not measured",
            "model_agreement": "not applicable — single deterministic rule set",
            "quality_flags": {k: v for k, v in quality.items() if v},
        },
        "cause": cause,
        "pipeline_version": PIPELINE_VERSION,
        "scoring_version": result["scoring_version"],
        "normalization": normalization,
    }
