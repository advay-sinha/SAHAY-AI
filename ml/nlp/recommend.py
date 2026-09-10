"""Assistive recommendation rules. Deterministic, stdlib only.

A recommendation is a SUGGESTED pathway for a human executive to consider.
Nothing here contacts anyone, and nothing is ever marked as done: every
recommendation starts and stays `awaiting_decision` until an officer confirms,
modifies or rejects it (root CLAUDE.md invariant 4).

Each rule names the dimensions that justify it, so the rationale and the
supporting evidence are traceable to utterances.
"""

from typing import Any, Dict, List, Mapping

#: pathway id -> (label, retrieval query)
PATHWAYS: Dict[str, tuple] = {
    "emergency": ("Emergency support", "emergency immediate danger"),
    "police": ("Police intervention", "police threat intervention"),
    "witness_protection": ("Witness protection", "witness protection complaint threat"),
    "medical": ("Medical assistance", "medical injury treatment"),
    "legal_aid": ("Legal aid", "legal aid complaint fir"),
    "counselling": ("Counselling support", "counselling support distress"),
}


def _dim(dims: Mapping[str, Mapping[str, Any]], d: str) -> tuple:
    v = dims.get(d) or {}
    return (v.get("score") or 0.0, v.get("confidence") or 0.0, list(v.get("evidence_turn_ids") or []))


def recommend(dims: Mapping[str, Mapping[str, Any]], band: Any, crisis: bool) -> List[Dict[str, Any]]:
    """Return suggested pathways with rationale, evidence and confidence."""
    d1, c1, e1 = _dim(dims, "D1")
    _d2, c2, e2 = _dim(dims, "D2")
    d3, c3, e3 = _dim(dims, "D3")
    d5, c5, e5 = _dim(dims, "D5")
    d7, c7, e7 = _dim(dims, "D7")
    d8, c8, e8 = _dim(dims, "D8")

    out: List[Dict[str, Any]] = []

    def add(pathway: str, rationale: str, evidence: List[str], confidence: float, basis: List[str]) -> None:
        if not evidence:
            return
        out.append({
            "action_type": pathway,
            "label": PATHWAYS[pathway][0],
            "query": PATHWAYS[pathway][1],
            "rationale": rationale,
            "evidence_turn_ids": sorted(set(evidence)),
            "confidence": round(confidence, 3),
            "basis_dimensions": basis,
            "status": "awaiting_decision",
        })

    if crisis or band == "Critical" or d1 >= 85:
        add("emergency",
            "The conversation contains language indicating immediate danger or crisis. "
            "An officer should consider immediate support.",
            e1 + e2, max(c1, c2), ["D1", "D2"])
    if d3 >= 80 or d1 >= 60:
        add("police",
            "The person describes threats or intimidation. An officer should consider "
            "whether police intervention is appropriate.",
            e3 + e1, min([c for c in (c3, c1) if c] or [0.0]), ["D1", "D3"])
    if d3 >= 80 and d8 >= 60:
        add("witness_protection",
            "Threats are described in connection with a complaint. An officer should "
            "consider whether witness-protection measures apply.",
            e3 + e8, min(c3, c8), ["D3", "D8"])
    if d7 >= 65:
        add("medical",
            "Someone is described as injured or needing treatment. An officer should "
            "consider arranging medical assistance.",
            e7, c7, ["D7"])
    if d8 >= 65:
        add("legal_aid",
            "A complaint or police contact is mentioned. An officer should consider "
            "whether legal aid would help.",
            e8, c8, ["D8"])
    if d5 >= 60 or d3 >= 60:
        add("counselling",
            "The person describes fear or ongoing distress. An officer should consider "
            "offering counselling support.",
            e5 + e3, max(c5, c3), ["D3", "D5"])
    return out
