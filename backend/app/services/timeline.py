"""Victim-safe timeline projection.

GET /cases/{id}/timeline must contain no assessment field (CONTRACTS.md
section 4). This module builds that view with an explicit allowlist rather
than by removing fields from a richer object: a denylist silently leaks every
field someone adds later.

Standard library only, so the leakage test runs with no installed dependency.
"""

from typing import Any, Dict, Iterable, List, Mapping

#: The only keys a timeline entry may contain. CONTRACTS.md section 2,
#: timeline.update {stage, label, ts}.
TIMELINE_ENTRY_KEYS = ("stage", "label", "ts")

#: Stages a victim sees. Deliberately about process, not about assessment:
#: "you are heard, this is your reference number, this is what happens next".
STAGES = (
    "request_received",
    "recorded",
    "under_review",
    "officer_assigned",
    "officer_speaking",
    "closed",
)


def timeline_entry(stage: str, label: str, ts: str) -> Dict[str, Any]:
    return {"stage": stage, "label": label, "ts": ts}


def project(entries: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Project arbitrary internal entries down to the victim-safe shape."""
    return [
        {key: entry.get(key) for key in TIMELINE_ENTRY_KEYS}
        for entry in entries
    ]


def victim_timeline(case_reference: str, entries: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """The complete GET /cases/{id}/timeline response body for a victim."""
    return {
        "reference": case_reference,
        "timeline": project(entries),
    }
