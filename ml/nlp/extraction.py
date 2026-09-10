"""Structured-record extraction schema.

Mirrors case.structured in CONTRACTS.md section 3. Slots filled from the free
narrative are marked source="extracted"; slots the victim answered directly are
marked source="answered". The dialogue policy never skips S2 on an extracted
value.
"""

from typing import Any, Dict

SLOT_NAMES = (
    "incident",
    "persons",
    "location",
    "time",
    "safety_now",
    "proximity_of_threat",
    "medical_need",
    "urgency",
    "relationship",
    "when",
    "where",
    "threat_ongoing",
    "intimidation",
    "witness_concern",
    "isolation",
    "displacement",
    "support_person",
    "fir_status",
    "legal_help",
    "requested_support",
)

SOURCE_EXTRACTED = "extracted"
SOURCE_ANSWERED = "answered"


def empty_record() -> Dict[str, Any]:
    return {
        "incident": None,
        "timeline": [],
        "persons": [],
        "threats": [],
        "safety_now": None,
        "medical_need": None,
        "legal_status": None,
        "isolation": None,
        "requested_support": None,
        "_sources": {},
    }


def mark(slots: Dict[str, Any], name: str, value: Any, source: str) -> Dict[str, Any]:
    slots[name] = value
    slots.setdefault("_sources", {})[name] = source
    return slots
