"""Structured-record extraction. Deterministic, stdlib only.

Mirrors case.structured in CONTRACTS.md section 3. Every populated field carries
the victim turn ids it came from ("every field links to its source utterance",
HANDOVER.md section 14). Text is kept in the original language; nothing is
translated or paraphrased.

Slots filled from the free narrative are marked source="extracted"; slots the
victim answered directly are marked source="answered". The dialogue policy never
skips S2 on an extracted value.
"""

from typing import Any, Dict, Iterable, List, Mapping

from .detectors import match_turn
from .lexicons import PERSON_TERMS, SAFE_NOW_TERMS, TIME_TERMS

SOURCE_EXTRACTED = "extracted"
SOURCE_ANSWERED = "answered"

SLOT_NAMES = (
    "incident", "persons", "location", "time", "safety_now", "proximity_of_threat",
    "medical_need", "urgency", "relationship", "when", "where", "threat_ongoing",
    "intimidation", "witness_concern", "isolation", "displacement", "support_person",
    "fir_status", "legal_help", "requested_support",
)

#: Which slots a victim answer fills, by the dialogue state it was given in.
ANSWERED_SLOTS: Dict[str, tuple] = {
    "S2": ("safety_now", "proximity_of_threat"),
    "S3": ("medical_need",),
    "S4": ("persons", "when"),
    "S5": ("threat_ongoing",),
    "S6": ("isolation",),
    "S7": ("fir_status",),
    "S8": ("requested_support",),
}

#: The narrative counts as told once this much has been heard in S1.
NARRATIVE_MIN_TURNS = 2
NARRATIVE_MIN_CHARS = 200

EXCERPT = 280


def _field(value: Any, turn_ids: List[str]) -> Dict[str, Any]:
    return {"value": value, "source_turn_ids": turn_ids}


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1] + "…"


def _contains(text: str, terms: Iterable[str]) -> List[str]:
    folded = text.casefold()
    return [t for t in terms if t.casefold() in folded]


def empty_record() -> Dict[str, Any]:
    return {
        "incident": None, "timeline": [], "persons": [], "threats": [],
        "safety_now": None, "medical_need": None, "legal_status": None,
        "isolation": None, "requested_support": None,
    }


def extract(victim_turns: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build case.structured from victim turns (each: id, text, state)."""
    turns = list(victim_turns)
    record = empty_record()

    narrative = [t for t in turns if match_any(t)] or turns[:1]
    if narrative:
        first = narrative[0]
        record["incident"] = _field(_excerpt(str(first["text"])), [str(first["id"])])

    for t in turns:
        text, tid = str(t["text"]), str(t["id"])
        for term in _contains(text, TIME_TERMS):
            record["timeline"].append(_field(term, [tid]))
        for term in _contains(text, PERSON_TERMS):
            if not any(p["value"] == term for p in record["persons"]):
                record["persons"].append(_field(term, [tid]))
        if match_turn("D3", text) or match_turn("D1", text):
            record["threats"].append(_field(_excerpt(text), [tid]))

    def ids_for(dim: str) -> List[str]:
        return [str(t["id"]) for t in turns if match_turn(dim, str(t["text"]))]

    med = ids_for("D7")
    if med:
        record["medical_need"] = _field("reported", med)
    legal = ids_for("D8")
    if legal:
        record["legal_status"] = _field("complaint or police contact mentioned", legal)
    iso = ids_for("D6")
    if iso:
        record["isolation"] = _field("reported", iso)

    danger = ids_for("D1")
    safe = [str(t["id"]) for t in turns if _contains(str(t["text"]), SAFE_NOW_TERMS)]
    s2 = [str(t["id"]) for t in turns if t.get("state") == "S2"]
    if danger and safe:
        record["safety_now"] = _field("conflicting", sorted(set(danger + safe)))
    elif danger:
        record["safety_now"] = _field("threat reported", danger)
    elif safe or s2:
        record["safety_now"] = _field("reported safe" if safe else "answered", safe or s2)

    s8 = [t for t in turns if t.get("state") == "S8"]
    if s8:
        record["requested_support"] = _field(_excerpt(str(s8[-1]["text"])), [str(s8[-1]["id"])])

    return record


def match_any(turn: Mapping[str, Any]) -> bool:
    text = str(turn.get("text", ""))
    return any(match_turn(d, text) for d in ("D1", "D3", "D6", "D7", "D8", "D9", "D5"))


def conflicting_safety(record: Mapping[str, Any]) -> bool:
    field = record.get("safety_now") or {}
    return isinstance(field, Mapping) and field.get("value") == "conflicting"


def dialogue_slots(victim_turns: Iterable[Mapping[str, Any]], record: Mapping[str, Any]) -> Dict[str, Any]:
    """Slots for dialogue.next: answered ones from the state they were given in,
    extracted ones from the structured record."""
    turns = list(victim_turns)
    slots: Dict[str, Any] = {"_sources": {}}

    def put(name: str, value: Any, source: str) -> None:
        if name in slots and slots["_sources"].get(name) == SOURCE_ANSWERED:
            return  # an answer is never downgraded to an extraction
        slots[name] = value
        slots["_sources"][name] = source

    s1 = [t for t in turns if t.get("state") in ("S1", None, "S0")]
    if len(s1) >= NARRATIVE_MIN_TURNS or sum(len(str(t["text"])) for t in s1) >= NARRATIVE_MIN_CHARS:
        put("incident", "told", SOURCE_EXTRACTED)

    for t in turns:
        for name in ANSWERED_SLOTS.get(str(t.get("state")), ()):
            put(name, str(t["id"]), SOURCE_ANSWERED)

    if record.get("medical_need"):
        put("medical_need", "reported", SOURCE_EXTRACTED)
    if record.get("legal_status"):
        put("fir_status", "mentioned", SOURCE_EXTRACTED)
    if record.get("isolation"):
        put("isolation", "reported", SOURCE_EXTRACTED)
    if record.get("threats"):
        put("threat_ongoing", "reported", SOURCE_EXTRACTED)
    if record.get("persons") and record.get("timeline"):
        put("persons", "mentioned", SOURCE_EXTRACTED)
        put("when", "mentioned", SOURCE_EXTRACTED)
    return slots
