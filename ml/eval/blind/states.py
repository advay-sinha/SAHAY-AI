"""The corpus status workflow and its transition ledger. Standard library only.

A sample moves through explicit states, and every move is a record in an
append-only hash chain. The point is not bookkeeping: it is that nobody can
turn a fresh submission into frozen evaluation evidence in one step, or
quietly clear a privacy or contamination flag without leaving a signed reason
behind.

States

  submitted                      accepted into the private root, nothing checked yet
  schema_invalid                 failed schema validation; kept for the record
  pii_review_required            the PII screen found a shape a human must look at
  contamination_review_required  the leakage checks found overlap with an exposed corpus
  assigned                       reviewers allocated
  under_review                   at least one review recorded, not yet enough
  conflicted                     reviewers disagree
  needs_adjudication             the disagreement has been routed to an adjudicator
  rejected                       terminal: not part of the corpus, never deleted
  review_complete                required reviews recorded and reconciled
  eligible                       every gate passed; may be frozen
  frozen                         part of an immutable frozen corpus version
  evaluated                      the pipeline has been run on it
  contaminated_after_evaluation  terminal: results published, no longer independent

There is no transition from ``submitted`` to ``frozen``, and no transition
into ``eligible`` that does not pass through ``review_complete``. The
transition table below is the whole rule; ``validate_transition`` is the only
way to move, and it is used by every command.

Each transition record carries the actor, the timestamp, the prior state, the
new state, a written reason, the hash of the input that justified the move,
and its own record hash. ``input_sha256`` is what makes a transition
falsifiable later: a move to ``review_complete`` names the review records it
rests on, a move to ``eligible`` names the eligibility report, and a move to
``frozen`` names the freeze manifest.
"""

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Mapping, Tuple

from .identity import validate_person
from .submission import canonical

RECORD_VERSION = "1.0.0"

STATES: Tuple[str, ...] = (
    "submitted",
    "schema_invalid",
    "pii_review_required",
    "contamination_review_required",
    "assigned",
    "under_review",
    "conflicted",
    "needs_adjudication",
    "rejected",
    "review_complete",
    "eligible",
    "frozen",
    "evaluated",
    "contaminated_after_evaluation",
)

TERMINAL = ("rejected", "contaminated_after_evaluation")

#: state -> states it may move to. Anything absent is refused.
TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "submitted": ("schema_invalid", "pii_review_required", "contamination_review_required",
                  "assigned", "rejected"),
    "schema_invalid": ("rejected",),
    "pii_review_required": ("contamination_review_required", "assigned", "rejected"),
    "contamination_review_required": ("assigned", "rejected"),
    "assigned": ("under_review", "rejected"),
    "under_review": ("under_review", "conflicted", "review_complete", "rejected"),
    "conflicted": ("needs_adjudication", "rejected"),
    "needs_adjudication": ("under_review", "review_complete", "rejected"),
    "review_complete": ("eligible", "conflicted", "rejected"),
    "eligible": ("frozen", "review_complete", "rejected"),
    "frozen": ("evaluated",),
    "evaluated": ("contaminated_after_evaluation",),
    "rejected": (),
    "contaminated_after_evaluation": (),
}

#: Moves that need a specific justification, not merely a reason string.
REQUIRES_INPUT = ("assigned", "under_review", "review_complete", "eligible", "frozen", "evaluated")

RECORD_FIELDS = {"record_version", "corpus_version", "submission_id", "actor", "timestamp",
                 "prior_state", "new_state", "reason", "input_sha256", "record_sha256"}
_HASHED_FIELDS = sorted(RECORD_FIELDS - {"record_sha256"})

MIN_REASON = 10
_ZERO = "0" * 64


class StateError(Exception):
    """An invalid, skipped or unjustified status transition."""


def record_sha256(record: Mapping[str, Any]) -> str:
    payload = {k: record[k] for k in _HASHED_FIELDS if k in record}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def input_hash(payload: Any) -> str:
    """Hash of whatever justified a transition. Content never leaves this function."""
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def validate_transition(prior: str, new: str) -> None:
    """Raise unless ``prior -> new`` is in the table."""
    if prior not in STATES:
        raise StateError(f"unknown prior state {prior!r}")
    if new not in STATES:
        raise StateError(f"unknown state {new!r}")
    if prior in TERMINAL:
        raise StateError(f"{prior} is terminal; a sample cannot leave it")
    if new not in TRANSITIONS[prior]:
        raise StateError(f"{prior} -> {new} is not a permitted transition")


def make_transition(corpus_version: str, submission_id: str, actor: Mapping[str, Any],
                    prior: str, new: str, reason: str, justification: Any,
                    timestamp: str) -> Dict[str, Any]:
    """Build one validated transition record. Raises rather than guessing."""
    validate_transition(prior, new)
    record = {
        "record_version": RECORD_VERSION,
        "corpus_version": corpus_version,
        "submission_id": submission_id,
        "actor": dict(actor),
        "timestamp": timestamp,
        "prior_state": prior,
        "new_state": new,
        "reason": reason,
        "input_sha256": input_hash(justification) if justification is not None else _ZERO,
    }
    record["record_sha256"] = record_sha256(record)
    errs = validate_record(record)
    if errs:
        raise StateError("; ".join(errs))
    return record


def validate_record(record: Mapping[str, Any]) -> List[str]:
    """Every problem with one transition record. Empty means valid."""
    errs: List[str] = []
    if not isinstance(record, Mapping):
        return ["transition record must be a JSON object"]
    extra = set(record) - RECORD_FIELDS
    missing = RECORD_FIELDS - set(record)
    if extra:
        errs.append(f"unknown fields {sorted(extra)}")
    if missing:
        return errs + [f"missing fields {sorted(missing)}"]
    if record["record_version"] != RECORD_VERSION:
        errs.append(f"record_version must be {RECORD_VERSION}")
    errs.extend(validate_person(record["actor"], "actor"))
    try:
        validate_transition(str(record["prior_state"]), str(record["new_state"]))
    except StateError as exc:
        errs.append(str(exc))
    if len(str(record["reason"]).strip()) < MIN_REASON:
        errs.append(f"a written reason of at least {MIN_REASON} characters is required")
    digest = str(record["input_sha256"])
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        errs.append("input_sha256 must be a sha256 hex digest")
    elif digest == _ZERO and record["new_state"] in REQUIRES_INPUT:
        errs.append(f"a transition to {record['new_state']} must name the input that justifies it")
    try:
        ts = datetime.fromisoformat(str(record["timestamp"]))
        if ts.tzinfo is None:
            errs.append("timestamp needs a timezone offset")
    except ValueError:
        errs.append("timestamp must be ISO 8601 with a timezone")
    if record["record_sha256"] != record_sha256(record):
        errs.append("record_sha256 does not match the record")
    return errs


def replay(records: Mapping[str, Any]) -> Dict[str, str]:
    """Current state per submission, by replaying transitions in ledger order.

    Raises on the first illegal move, so a ledger that was appended to out of
    order, or that skips a state, cannot be read as a valid history.
    """
    current: Dict[str, str] = {}
    for record in records:
        sid = str(record["submission_id"])
        prior = current.get(sid, "submitted")
        if str(record["prior_state"]) != prior:
            raise StateError(f"{sid}: transition claims prior state {record['prior_state']!r}, "
                             f"history says {prior!r}")
        validate_transition(prior, str(record["new_state"]))
        current[sid] = str(record["new_state"])
    return current


def reachable(target: str) -> List[str]:
    """Every state from which ``target`` is directly reachable. For documentation."""
    return sorted(s for s, nexts in TRANSITIONS.items() if target in nexts)


assert set(TRANSITIONS) == set(STATES)
assert "frozen" not in TRANSITIONS["submitted"]
assert reachable("eligible") == ["review_complete"]
assert reachable("frozen") == ["eligible"]
