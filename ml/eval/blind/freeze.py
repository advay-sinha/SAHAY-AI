"""The freeze gate and the artefacts a freeze produces. Standard library only.

Freezing is the moment a pile of human work becomes evaluation evidence, and
it is the last moment anything can be checked. The gate therefore refuses by
default and states every reason it refused, so a partial corpus produces a
work list rather than a number.

Conditions, all of which must hold

   1. the coverage plan for this version is satisfied, per language;
   2. every sample still passes schema validation;
   3. the required human reviews exist;
   4. reviewer roles and language competencies are recorded and adequate;
   5. no author reviewed their own sample;
   6. crisis and immediate-danger labels rest on two agreeing human reviewers;
   7. every conflict has been adjudicated and resolved;
   8. every PII and contamination flag has been cleared by a human, with a reason;
   9. no sample, and no declared derivative of one, appears in an exposed or
      training corpus;
  10. the review ledger verifies end to end;
  11. the adjudication ledger verifies end to end;
  12. every content hash still matches its submission;
  13. no prediction has been produced for this corpus version;
  14. this corpus version has not already been frozen.

What a freeze writes, OUTSIDE Git
  corpus.json          the immutable canonical scenarios
  labels.json          the frozen human labels, evidence turns and routing
  review_manifest.json who reviewed what, with record hashes and no reasoning text
  coverage_report.json the coverage accounting
  freeze_manifest.json hashes, counts, summaries, ledger heads, actor, timestamp

What may be committed
  ``public_manifest()`` returns the content-free subset: version, counts,
  language / category / slice totals, file hashes, ledger heads, freeze
  timestamp. No scenario text, no per-narrative label, no reviewer reasoning.
  It is written only when a real freeze happened. A manifest for zero human
  samples would be a fabrication, so ``freeze()`` refuses before writing
  anything at all.
"""

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..schema import CATEGORIES, CRITICAL_CATEGORIES, DETECTOR_CATEGORIES
from . import leakage as lk
from .assignment import CRITICAL_AGREEMENT, REVIEWS_PER_SAMPLE, critical_support
from .ledger import LedgerError, read
from .plan import CATEGORY_NAMES, SLICE_NAMES
from .submission import canonical, content_sha256, narrative_sha256

FREEZE_VERSION = "1.0.0"


class FreezeError(Exception):
    """The freeze gate refused, or a frozen corpus failed to verify."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_payload(payload: Any) -> str:
    return json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def preconditions(store: Any, index: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Evaluate all fourteen conditions without writing anything.

    Returns ``{"ok": bool, "refusals": [{"condition", "detail"}], ...}``.
    Details carry ids, counts and reason classes; never scenario text.
    """
    index = index if index is not None else lk.build_index()
    refusals: List[Dict[str, Any]] = []

    def refuse(condition: str, detail: str) -> None:
        refusals.append({"condition": condition, "detail": detail})

    # 14. already frozen
    if store.frozen_manifest() is not None:
        refuse("version_not_already_frozen",
               f"corpus version {store.version} already has a freeze manifest")

    # 10 / 11. ledgers verify
    for name in ("submissions", "reviews", "adjudications", "states"):
        try:
            read(store.ledger(name))
        except LedgerError as exc:
            refuse("ledgers_verify", f"{name} ledger: {exc}")

    if any(r["condition"] == "ledgers_verify" for r in refusals):
        return {"ok": False, "refusals": refusals, "eligible": [], "coverage": None}

    eligibility = store.eligibility(index)
    eligible = list(eligibility["eligible"])
    submissions = store.submissions()

    # 2, 3, 4, 5, 6, 7, 8, 12 come back as eligibility reason classes.
    reason_to_condition = {
        "schema_invalid": "schema_valid",
        "content_hash_mismatch": "content_hashes_match",
        "missing_human_review": "required_reviews_exist",
        "reviews_not_from_distinct_humans": "required_reviews_exist",
        "reviewer_language_competency": "reviewer_competency",
        "author_reviewed_own_sample": "author_did_not_review",
        "critical_needs_two_agreeing_reviewers": "critical_review_counts",
        "unresolved_conflict": "conflicts_adjudicated",
        "no_agreed_outcome": "conflicts_adjudicated",
        "pii_review_open": "flags_resolved",
        "contamination_review_open": "flags_resolved",
        "exposed_corpus_overlap": "no_exposed_overlap",
        "derived_from_exposed_sample": "no_exposed_overlap",
    }
    blocked: Dict[str, List[str]] = {}
    for sid, row in sorted(eligibility["rows"].items()):
        for reason in row["reasons"]:
            condition = reason_to_condition.get(reason, "sample_state")
            blocked.setdefault(condition, []).append(sid)
    for condition, ids in sorted(blocked.items()):
        refuse(condition, f"{len(ids)} sample(s): {', '.join(sorted(ids)[:10])}"
                          + (" ..." if len(ids) > 10 else ""))

    # 13. no predictions produced for this version
    if store.predictions_recorded():
        refuse("no_predictions_before_freeze",
               "evaluation output already exists for this corpus version; it is no longer unseen")

    # 9. explicit re-check of exposure for the proposed set (belt and braces)
    for sid in eligible:
        findings = lk.check(submissions[sid], index)
        if lk.worst(findings) == "block":
            refuse("no_exposed_overlap", f"{sid}: overlaps an exposed corpus")

    # 1. coverage
    coverage = store.coverage_report(eligible) if eligible else None
    if not eligible:
        refuse("coverage_plan_satisfied", "no eligible human-authored samples")
    elif not coverage["satisfied"]:
        refuse("coverage_plan_satisfied",
               f"{len(coverage['shortfalls'])} shortfall(s); {coverage['samples']} of "
               f"{coverage['total_min']} samples")

    return {"ok": not refusals, "refusals": refusals, "eligible": eligible, "coverage": coverage}


def build_artefacts(store: Any, eligible: Sequence[str], coverage: Mapping[str, Any],
                    actor: Mapping[str, Any], timestamp: str) -> Dict[str, Any]:
    """The four content files plus the freeze manifest. Pure given the store."""
    submissions = store.submissions()
    corpus: List[Dict[str, Any]] = []
    labels: List[Dict[str, Any]] = []
    review_manifest: List[Dict[str, Any]] = []
    reviewer_counts: Dict[str, int] = {}

    for sid in sorted(eligible):
        submission = submissions[sid]
        outcome = store.outcome(sid)
        if outcome is None:
            raise FreezeError(f"{sid}: no agreed human outcome at freeze time")
        corpus.append({
            "submission_id": sid,
            "corpus_version": store.version,
            "language": submission["language"],
            "script": submission["script"],
            "turns": submission["turns"],
            "content_sha256": content_sha256(submission),
            "narrative_sha256": narrative_sha256(submission),
        })
        labels.append({
            "submission_id": sid,
            "labels": outcome["labels"],
            "routing": outcome["routing"],
            "expected_evidence": outcome["expected_evidence"],
            "expected_abstention": outcome["expected_abstention"],
            "declared_slices": list(submission.get("intended_slices") or []),
            "label_source": outcome["source"],
        })
        reviews = store.reviews(sid)
        review_manifest.append({
            "submission_id": sid,
            "reviews": [{"person_id": r["reviewer"]["person_id"], "role": r["reviewer"]["role"],
                         "languages": r["reviewer"]["languages"],
                         "code_switch_competent": r["reviewer"]["code_switch_competent"],
                         "decision": r["decision"], "confidence": r["confidence"],
                         "ambiguity_flags": r["ambiguity_flags"],
                         "record_sha256": r["record_sha256"], "timestamp": r["timestamp"]}
                        for r in sorted(reviews, key=lambda x: str(x["record_sha256"]))],
            "adjudications": [{"person_id": a["adjudicator"]["person_id"], "role": a["adjudicator"]["role"],
                               "resolution_basis": a["resolution_basis"],
                               "critical_conflict_resolved": a["critical_conflict_resolved"],
                               "record_sha256": a["record_sha256"], "timestamp": a["timestamp"]}
                              for a in store.adjudications(sid)],
            "critical": any(bool(outcome["labels"].get(c)) for c in CRITICAL_CATEGORIES),
            "critical_support": critical_support(reviews, outcome),
        })
        for r in reviews:
            pid = str(r["reviewer"]["person_id"])
            reviewer_counts[pid] = reviewer_counts.get(pid, 0) + 1

    files = {"corpus": corpus, "labels": labels, "review_manifest": review_manifest,
             "coverage_report": dict(coverage)}
    per_file = {name: _sha256_text(_file_payload(payload)) for name, payload in files.items()}
    corpus_sha256 = hashlib.sha256(canonical(corpus).encode("utf-8")).hexdigest()

    manifest = {
        "freeze_version": FREEZE_VERSION,
        "corpus_version": store.version,
        "plan_version": coverage["plan_version"],
        "frozen_at": timestamp,
        "frozen_by": {"person_id": actor["person_id"], "identity": actor["identity"], "role": actor["role"]},
        "samples": len(corpus),
        "corpus_sha256": corpus_sha256,
        "file_sha256": per_file,
        "by_language": coverage["by_language"],
        "by_category": {c: coverage["by_category"][c]["total"] for c in CATEGORY_NAMES},
        "by_slice": {s: coverage["by_slice"][s]["total"] for s in SLICE_NAMES},
        "reviewers": {"distinct_humans": len(reviewer_counts),
                      "reviews_total": sum(reviewer_counts.values()),
                      "reviews_per_human": dict(sorted(reviewer_counts.items())),
                      "reviews_per_sample_required": REVIEWS_PER_SAMPLE,
                      "critical_agreement_required": CRITICAL_AGREEMENT},
        "ledger_heads": store.heads(),
        "label_schema_categories": list(CATEGORIES),
        "detector_categories": list(DETECTOR_CATEGORIES),
        "predictions_run": False,
        "exposed": False,
    }
    files["freeze_manifest"] = manifest
    return files


def freeze(store: Any, actor: Mapping[str, Any], timestamp: str,
           index: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Run the gate and, only if every condition holds, write the artefacts."""
    gate = preconditions(store, index)
    if not gate["ok"]:
        raise FreezeError("freeze refused: " + "; ".join(
            f"{r['condition']} ({r['detail']})" for r in gate["refusals"]))
    files = build_artefacts(store, gate["eligible"], gate["coverage"], actor, timestamp)
    written = store.write_frozen(files)
    for sid in gate["eligible"]:
        store.move(sid, "frozen", actor, f"frozen into corpus {store.version}",
                   {"corpus_sha256": files["freeze_manifest"]["corpus_sha256"]}, timestamp)
    return {"manifest": files["freeze_manifest"], "files": {k: str(v.name) for k, v in written.items()},
            "samples": len(files["corpus"])}


def public_manifest(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """The Git-safe subset of a freeze manifest: counts and hashes, nothing else."""
    return {
        "freeze_version": manifest["freeze_version"],
        "corpus_version": manifest["corpus_version"],
        "plan_version": manifest["plan_version"],
        "frozen_at": manifest["frozen_at"],
        "samples": manifest["samples"],
        "corpus_sha256": manifest["corpus_sha256"],
        "file_sha256": dict(manifest["file_sha256"]),
        "by_language": dict(manifest["by_language"]),
        "by_category": dict(manifest["by_category"]),
        "by_slice": dict(manifest["by_slice"]),
        "reviewers": {"distinct_humans": manifest["reviewers"]["distinct_humans"],
                      "reviews_total": manifest["reviewers"]["reviews_total"],
                      "reviews_per_sample_required": manifest["reviewers"]["reviews_per_sample_required"],
                      "critical_agreement_required": manifest["reviewers"]["critical_agreement_required"]},
        "ledger_heads": dict(manifest["ledger_heads"]),
        "note": ("Content-free. No scenario text, no label tied to a narrative, no reviewer identity and no "
                 "reviewer reasoning. The corpus itself lives outside Git under SAHAY_EVAL_ROOT."),
    }


def verify_frozen(store: Any) -> List[str]:
    """Re-verify a frozen corpus against its manifest. Empty means intact."""
    manifest = store.frozen_manifest()
    if manifest is None:
        return ["no freeze manifest for this corpus version"]
    problems: List[str] = []
    for name, digest in sorted(manifest["file_sha256"].items()):
        try:
            payload = store.read_frozen(name)
        except Exception:
            problems.append(f"{name}.json is missing or unreadable")
            continue
        if _sha256_text(_file_payload(payload)) != digest:
            problems.append(f"{name}.json does not match its recorded sha256")
    try:
        corpus = store.read_frozen("corpus")
        if hashlib.sha256(canonical(corpus).encode("utf-8")).hexdigest() != manifest["corpus_sha256"]:
            problems.append("corpus_sha256 does not match the frozen corpus")
    except Exception:
        problems.append("corpus.json is missing or unreadable")
    for name, recorded in sorted(manifest["ledger_heads"].items()):
        try:
            from .ledger import verify_head
            verify_head(store.ledger(name), recorded)
        except LedgerError as exc:
            problems.append(f"{name} ledger: {exc}")
    return problems
