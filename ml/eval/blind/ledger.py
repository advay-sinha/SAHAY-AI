"""Append-only SHA-256 hash-chained ledgers for the blind corpus. Stdlib only.

This is the SAME mechanism the fixture review ledger already uses, generalised
to four chains (submissions, reviews, adjudications, state transitions) that
live outside Git under the private evaluation root. The primitives are
imported from ``ml.eval.review_workflow`` rather than re-implemented, so there
is one canonicalisation and one entry-hash definition in the repository.

Entry shape, one JSON object per line:

    {"seq": 1, "prev_hash": "<64 hex>", "kind": "review",
     "record_id": "<sha256 of the canonical record>",
     "record": {...}, "entry_hash": "<sha256 of the entry without entry_hash>"}

``prev_hash`` of the first entry is 64 zeros. Reading re-verifies every link,
so an edited, deleted, reordered or inserted entry is detected anywhere except
at the tail, and the same record cannot be appended twice.

Stated limits, not hidden ones
  * Truncating trailing entries, or rewriting the whole file with recomputed
    hashes, is only detectable against an externally recorded head. ``head()``
    prints ``<count>:<entry_hash>``; record it in the freeze manifest (which is
    committed) and in the backup log, and check it with ``verify_head``.
  * The chain is not signed. It proves *self-consistency and order*, not
    authorship. Authorship rests on the named human identity inside the record
    and on the attestation sentence that identity signed.
  * A ledger stored on one machine with no backup can be deleted outright. The
    recovery requirement is in ``ml/eval/BLIND_EVALUATION.md``.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..review_workflow import GENESIS, canonical, entry_hash, record_id

KINDS = ("submission", "review", "adjudication", "state")
ENTRY_FIELDS = {"seq", "prev_hash", "kind", "record_id", "record", "entry_hash"}

__all__ = ["LedgerError", "GENESIS", "KINDS", "canonical", "entry_hash", "record_id",
           "read", "append", "head", "verify_head", "records", "contains"]


class LedgerError(Exception):
    """The chain is broken, the record is a duplicate, or the head does not match."""


def read(path: Path) -> List[Dict[str, Any]]:
    """Read and verify a whole chain. An absent or empty ledger is valid and empty."""
    path = Path(path)
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    prev, seen = GENESIS, set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            raise LedgerError(f"ledger line {n}: not valid JSON") from None
        if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS or not isinstance(entry["record"], dict):
            raise LedgerError(f"ledger line {n}: entry fields must be exactly {sorted(ENTRY_FIELDS)}")
        if entry["kind"] not in KINDS:
            raise LedgerError(f"ledger line {n}: unknown record kind")
        if entry["seq"] != len(entries) + 1:
            raise LedgerError(f"ledger line {n}: seq {entry['seq']!r}, expected {len(entries) + 1} "
                              "(entry deleted, inserted or reordered)")
        if entry["prev_hash"] != prev:
            raise LedgerError(f"ledger line {n}: prev_hash does not link to the previous entry (chain broken)")
        if entry["record_id"] != record_id(entry["record"]):
            raise LedgerError(f"ledger line {n}: record_id does not match its record (record modified)")
        if entry["entry_hash"] != entry_hash(entry):
            raise LedgerError(f"ledger line {n}: entry_hash does not match the entry (entry modified)")
        if entry["record_id"] in seen:
            raise LedgerError(f"ledger line {n}: duplicate record")
        seen.add(entry["record_id"])
        prev = entry["entry_hash"]
        entries.append(entry)
    return entries


def append(path: Path, kind: str, record: Mapping[str, Any]) -> str:
    """Verify the chain, then append one record. Returns its record_id.

    Never rewrites a line: a superseded record is followed by a new record, and
    a duplicate is refused outright.
    """
    if kind not in KINDS:
        raise LedgerError(f"unknown record kind {kind!r}")
    path = Path(path)
    entries = read(path)
    rid = record_id(record)
    if any(e["record_id"] == rid for e in entries):
        raise LedgerError("this record has already been appended")
    entry: Dict[str, Any] = {"seq": len(entries) + 1,
                             "prev_hash": entries[-1]["entry_hash"] if entries else GENESIS,
                             "kind": kind, "record_id": rid, "record": dict(record)}
    entry["entry_hash"] = entry_hash(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:  # append-only, never "w"
        f.write(canonical(entry) + "\n")
    return rid


def head(path: Path) -> str:
    """``<count>:<last entry_hash>`` of a verified chain; ``0:<64 zeros>`` when empty."""
    entries = read(path)
    return f"{len(entries)}:{entries[-1]['entry_hash'] if entries else GENESIS}"


def verify_head(path: Path, expected: str) -> None:
    """Detect tail truncation or a recomputed rewrite against a recorded head."""
    try:
        count_s, want = str(expected).split(":")
        count = int(count_s)
    except ValueError:
        raise LedgerError("expected head must be <count>:<sha256>") from None
    entries = read(path)
    if count < 0 or len(entries) < count:
        raise LedgerError(f"ledger has {len(entries)} entries, the recorded head had {count} (truncated)")
    at = entries[count - 1]["entry_hash"] if count else GENESIS
    if at != want:
        raise LedgerError(f"entry {count} does not match the recorded head (ledger rewritten)")


def records(path: Path, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """Records of one kind, in ledger order, from a verified chain."""
    return [e["record"] for e in read(path) if kind is None or e["kind"] == kind]


def contains(path: Path, rid: str) -> bool:
    return any(e["record_id"] == rid for e in read(path))
