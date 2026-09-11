"""Run the deterministic text pipeline on one labelled sample and map its
output onto the label-schema categories.

Standard library only. It calls exactly what the backend calls
(`crisis_check` per victim turn, `assess` per conversation) and reads the
detector tiers through `match_turn`, the same function `score_dimension` uses.
It never re-implements a detector.

Category -> system signal (documented in ml/eval/README.md):
  crisis_self_harm            crisis pre-check fired on the turn
  immediate_danger            a D1 tier-3 (imminent presence) match on the turn
  continuing_threat           any D1 match, or a D3 match of tier >= 2
  medical_urgency             a D7 match of tier >= 2 (pain alone is tier 1)
  isolation_boycott_displacement  any D6 match
  legal_urgency               any D8 match
  communication_safety_coercion  any D9 match, or evidence of the coercion alert
  explicit_human_request      NOT IMPLEMENTED in text: the victim app sends a
                              request_human event from a button. Excluded from
                              metrics with that reason.
"""

from typing import Any, Dict, List, Mapping, Optional

from ..assessment import assess
from ..guardrails import crisis_check
from ..nlp.detectors import match_turn

#: Categories with no text detector, and why.
NOT_IMPLEMENTED = {
    "explicit_human_request": "no text detector; the app sends request_human from a button",
}


def _victim(sample: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [t for t in sample["turns"] if t["speaker"] == "victim"]


def _turns_where(turns, dimension: str, min_tier: int = 1) -> List[str]:
    out = []
    for t in turns:
        found = match_turn(dimension, str(t["text"]))
        if found and found[0] >= min_tier:
            out.append(str(t["id"]))
    return out


def predict(sample: Mapping[str, Any]) -> Dict[str, Any]:
    """Return {categories: {cat: {predicted, evidence}}, routed_critical, ...}."""
    victim = _victim(sample)
    crisis_turns: List[str] = []
    crisis_attributed: List[str] = []
    crisis_suppressed: List[str] = []
    for t in victim:
        r = crisis_check(str(t["text"]))
        if r["crisis"]:
            crisis_turns.append(str(t["id"]))
            if all(m.get("context") == "attributed_to_third_party" for m in r["matches"]):
                crisis_attributed.append(str(t["id"]))
        elif r["suppressed"]:
            crisis_suppressed.append(str(t["id"]))

    turns = [{"id": t["id"], "speaker": t["speaker"], "text": t["text"], "state": t["state"]}
             for t in sample["turns"]]
    result = assess(turns, True, bool(crisis_turns), channel=sample["channel"])

    coercion = next((a for a in result["alerts"] if a["type"] == "coercion"), None)
    comm = sorted(set(_turns_where(victim, "D9")) | set((coercion or {}).get("evidence_turn_ids") or []))
    threat = sorted(set(_turns_where(victim, "D1")) | set(_turns_where(victim, "D3", 2)))

    evidence: Dict[str, Optional[List[str]]] = {
        "crisis_self_harm": crisis_turns,
        "immediate_danger": _turns_where(victim, "D1", 3),
        "continuing_threat": threat,
        "medical_urgency": _turns_where(victim, "D7", 2),
        "isolation_boycott_displacement": _turns_where(victim, "D6"),
        "legal_urgency": _turns_where(victim, "D8"),
        "communication_safety_coercion": comm,
        "explicit_human_request": None,
    }
    categories = {}
    for cat, ids in evidence.items():
        if ids is None:
            categories[cat] = {"predicted": None, "evidence": [], "excluded": NOT_IMPLEMENTED[cat]}
        else:
            categories[cat] = {"predicted": bool(ids), "evidence": list(ids)}

    # Every evidence id the pipeline itself cites, for the link-validity check.
    cited = {d: list(v.get("evidence_turn_ids") or []) for d, v in result["dims"].items()}
    cited.update({f"alert:{a['type']}": list(a["evidence_turn_ids"]) for a in result["alerts"]})
    cited.update({f"rec:{r['action_type']}": list(r["evidence_turn_ids"]) for r in result["recommendations"]})

    routed = bool(crisis_turns) or result["band"] == "Critical"
    return {
        "id": sample["id"],
        "categories": categories,
        "crisis_precheck": bool(crisis_turns),
        "crisis_attributed_turns": crisis_attributed,
        "crisis_suppressed_turns": crisis_suppressed,
        "routed_critical": routed,
        "band": result["band"],
        "svi": result["svi"],
        "abstained": result["band"] is None and not result["suppressed"],
        "abstention_reasons": list(result["abstention_reasons"]),
        "overrides_applied": list(result["overrides_applied"]),
        "d4": result["dims"].get("D4"),
        "normalization": result["normalization"],
        "cited_evidence": cited,
        "victim_turn_ids": [str(t["id"]) for t in victim],
        "scoring_version": result.get("scoring_version"),
        "pipeline_version": result.get("pipeline_version"),
    }
