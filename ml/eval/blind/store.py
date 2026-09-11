"""The private corpus store: everything the commands do to one corpus version.

Standard library only, and no prediction module anywhere in the import graph.

The store owns four append-only ledgers under the private root — submissions,
reviews, adjudications and state transitions — and derives everything else
from them. Files written next to the ledgers (one JSON per submission, per
packet, per record) are convenience copies for humans; the ledgers are the
truth, and a copy that disagrees with its ledger entry is a hash mismatch, not
a tie-break.

Three rules run through every method here.

  Nothing is invented. Every mutating operation takes an ``actor`` that must
  already be on the roster as a real human. A command cannot supply a review,
  an approval, a label or a clearance on anybody's behalf.

  Nothing is overwritten. A ledger is only ever appended to. A superseded or
  rejected record stays where it is, and a rejected submission keeps its
  reviews.

  Nothing narrative is logged. Every summary, status row and error message
  here carries ids, counts, hashes and reason classes. Scenario text is
  written only into the private per-submission files and the blinded packets,
  both of which live outside Git.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..schema import CRITICAL_CATEGORIES
from . import adjudication as adj
from . import annotation as ann
from . import leakage as lk
from . import states as st
from . import submission as sub
from .exit_codes import (EXIT_ADJUDICATION, EXIT_LEDGER, EXIT_SCHEMA, EXIT_USAGE)
from .assignment import (CRITICAL_AGREEMENT, REVIEWS_PER_SAMPLE, assign, assigned_to, compare_reviews,
                         critical_support, duplicate_reviewer, validate_roster)
from .identity import competent_for, same_person
from .ledger import LedgerError, append, head, records
from .paths import RootError, check_version, eval_root, init_root, ledger_path, resolve_under, version_dirs
from .plan import categories_of, coverage, load_plan


class StoreError(Exception):
    """A store operation was refused. The message names ids, never narrative.

    ``code`` is the documented process exit code for this refusal class, so the
    command line never has to guess a code by reading a message.
    """

    def __init__(self, message: str, code: int = EXIT_USAGE):
        super().__init__(message)
        self.code = code


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def _read_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StoreError(f"{Path(path).name} does not exist", EXIT_USAGE) from None
    except ValueError:
        raise StoreError(f"{Path(path).name} is not valid JSON", EXIT_SCHEMA) from None


class Store:
    """One corpus version inside one private evaluation root."""

    def __init__(self, root: Path, version: str = "v1", plan: Optional[Mapping[str, Any]] = None):
        self.root = Path(root).resolve()
        self.version = check_version(version)
        self.dirs = version_dirs(self.version)
        #: An explicit plan is for TESTS ONLY, so a miniature corpus can be
        #: driven end to end. The command line never passes one, so a real
        #: freeze is always measured against the committed, versioned plan.
        self._plan = dict(plan) if plan is not None else None

    # --- construction -----------------------------------------------------------------

    @classmethod
    def open(cls, root: str = "", version: str = "v1") -> "Store":
        return cls(eval_root(root), version)

    def plan(self) -> Dict[str, Any]:
        """The coverage plan this store is measured against."""
        return dict(self._plan) if self._plan is not None else load_plan(self.version)

    def path(self, key: str, *parts: str) -> Path:
        rel = self.dirs[key]
        for part in parts:
            rel = f"{rel}/{part}"
        return resolve_under(self.root, rel)

    def ledger(self, name: str) -> Path:
        return ledger_path(self.root, self.version, name)

    def init(self) -> Dict[str, Any]:
        """Create the layout and drop blank templates into ``intake/``."""
        made = init_root(self.root, self.version)
        intake = resolve_under(self.root, "intake")
        written = []
        for lang in ("en", "hi", "hinglish"):
            written.append(_write_json(intake / f"submission-template-{lang}.json",
                                       sub.template(self.version, lang)))
        written.append(_write_json(intake / "roster-template.json",
                                   {"roster_version": "1.0.0", "corpus_version": self.version, "people": []}))
        written.append(_write_json(intake / "README.json", {
            "corpus_version": self.version,
            "what_this_is": "Blank templates. Copy one per scenario, fill it by hand, and validate it before "
                            "submitting. Nothing in this directory contains a scenario.",
            "next": ["blind_corpus validate-submission FILE",
                     "blind_corpus submit FILE --actor <person-id>",
                     "blind_corpus assign --actor <person-id>",
                     "blind_corpus export-review --actor <person-id>"],
            "never_commit": "No file under this root may be added to Git.",
        }))
        return {"directories": len(made), "templates": [p.name for p in written]}

    # --- roster -----------------------------------------------------------------------

    def roster_path(self) -> Path:
        return self.path("assignments", "roster.json")

    def roster(self) -> Dict[str, Any]:
        roster = _read_json(self.roster_path())
        errs = validate_roster(roster, self.version)
        if errs:
            raise StoreError("roster is invalid: " + "; ".join(errs), EXIT_SCHEMA)
        return roster

    def actor(self, person_id: str, capability: str = "") -> Dict[str, Any]:
        """Resolve a real human from the roster. Never fabricates one."""
        for person in self.roster()["people"]:
            if str(person["person_id"]) == str(person_id):
                if capability and not person.get(capability):
                    raise StoreError(f"{person_id} is not marked {capability} on the roster", EXIT_USAGE)
                return {k: person[k] for k in ("person_id", "identity", "kind", "role",
                                               "languages", "code_switch_competent")}
        raise StoreError(f"{person_id!r} is not on the roster for {self.version}; add the person first",
                         EXIT_USAGE)

    # --- ledger access ----------------------------------------------------------------

    def submissions(self) -> Dict[str, Dict[str, Any]]:
        """Submission id -> the LAST recorded version of that submission."""
        out: Dict[str, Dict[str, Any]] = {}
        for record in records(self.ledger("submissions"), "submission"):
            out[str(record["submission_id"])] = record
        return out

    def reviews(self, submission_id: str = "") -> List[Dict[str, Any]]:
        rows = records(self.ledger("reviews"), "review")
        return [r for r in rows if not submission_id or r["submission_id"] == submission_id]

    def adjudications(self, submission_id: str = "") -> List[Dict[str, Any]]:
        rows = records(self.ledger("adjudications"), "adjudication")
        return [r for r in rows if not submission_id or r["submission_id"] == submission_id]

    def transitions(self, submission_id: str = "") -> List[Dict[str, Any]]:
        rows = records(self.ledger("states"), "state")
        return [r for r in rows if not submission_id or r["submission_id"] == submission_id]

    def heads(self) -> Dict[str, str]:
        return {name: head(self.ledger(name)) for name in ("submissions", "reviews", "adjudications", "states")}

    def current_states(self) -> Dict[str, str]:
        return st.replay(self.transitions())

    def state_of(self, submission_id: str) -> str:
        return self.current_states().get(str(submission_id), "submitted")

    # --- transitions ------------------------------------------------------------------

    def move(self, submission_id: str, new_state: str, actor: Mapping[str, Any], reason: str,
             justification: Any, timestamp: str) -> str:
        prior = self.state_of(submission_id)
        record = st.make_transition(self.version, submission_id, actor, prior, new_state,
                                    reason, justification, timestamp)
        return append(self.ledger("states"), "state", record)

    # --- submissions ------------------------------------------------------------------

    def screen(self, submission: Mapping[str, Any],
               index: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Schema, PII and leakage results for one submission. Reads nothing else."""
        index = index if index is not None else lk.build_index()
        errors = sub.validate(submission, self.version)
        pii = sub.personal_information(submission)
        findings = lk.check(submission, index)
        return {"submission_id": submission.get("submission_id"), "schema_errors": errors,
                "pii": pii, "leakage": findings, "leakage_severity": lk.worst(findings)}

    def submit(self, submission: Mapping[str, Any], actor: Mapping[str, Any], timestamp: str,
               index: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Record one human-authored submission and its first state transitions."""
        sid = str(submission.get("submission_id", ""))
        existing = self.submissions()
        if sid in existing:
            raise StoreError(f"{sid} has already been submitted; a changed scenario needs a new id",
                             EXIT_USAGE)
        report = self.screen(submission, index)
        if report["schema_errors"]:
            raise StoreError(f"{sid}: schema invalid ({len(report['schema_errors'])} problem(s)); "
                             "nothing was recorded", EXIT_SCHEMA)
        rid = append(self.ledger("submissions"), "submission", submission)
        _write_json(self.path("submissions", f"{sid}.json"), submission)

        state, reason = "submitted", ""
        if report["pii"]:
            state = "pii_review_required"
            reason = f"PII screen matched {len(report['pii'])} pattern(s); a human must read the scenario"
        elif report["leakage_severity"]:
            state = "contamination_review_required"
            reason = (f"leakage checks returned {report['leakage_severity']} "
                      f"({len(report['leakage'])} finding(s))")
        if state != "submitted":
            self.move(sid, state, actor, reason,
                      {"pii": report["pii"], "leakage": report["leakage"]}, timestamp)
        return {"submission_id": sid, "record_id": rid, "state": self.state_of(sid), "screen": report}

    # --- assignment -------------------------------------------------------------------

    def assignment_path(self) -> Path:
        return self.path("assignments", "assignments.json")

    def build_assignment(self, reviews_per_sample: int = REVIEWS_PER_SAMPLE) -> Dict[str, Any]:
        ready = [s for sid, s in sorted(self.submissions().items())
                 if self.state_of(sid) in ("submitted", "assigned", "under_review")]
        return assign(ready, self.roster(), reviews_per_sample)

    def save_assignment(self, actor: Mapping[str, Any], timestamp: str,
                        reviews_per_sample: int = REVIEWS_PER_SAMPLE) -> Dict[str, Any]:
        allocation = self.build_assignment(reviews_per_sample)
        _write_json(self.assignment_path(), allocation)
        for row in allocation["assignments"]:
            sid = row["submission_id"]
            if self.state_of(sid) == "submitted" and row["assigned"] >= reviews_per_sample:
                self.move(sid, "assigned", actor,
                          f"{row['assigned']} independent reviewers allocated deterministically",
                          row, timestamp)
        return allocation

    def assignment(self) -> Dict[str, Any]:
        return _read_json(self.assignment_path())

    # --- review packets ---------------------------------------------------------------

    def export_packets(self) -> List[Path]:
        """One blinded packet per assigned reviewer. Never reads the review ledger."""
        allocation = self.assignment()
        roster = {str(p["person_id"]): p for p in self.roster()["people"]}
        submissions = self.submissions()
        written: List[Path] = []
        for row in allocation["assignments"]:
            submission = submissions.get(row["submission_id"])
            if submission is None:
                continue
            for entry in row["reviewers"]:
                person = roster.get(entry["person_id"])
                if person is None:
                    raise StoreError(f"{entry['person_id']} is assigned but no longer on the roster", EXIT_USAGE)
                packet = ann.build_packet(submission, person)
                written.append(_write_json(
                    self.path("packets", f"{row['submission_id']}--{entry['person_id']}.json"), packet))
        return written

    def packet_for(self, submission_id: str, person_id: str) -> Dict[str, Any]:
        submission = self.submissions().get(str(submission_id))
        if submission is None:
            raise StoreError(f"{submission_id} is not a recorded submission", EXIT_USAGE)
        person = next((p for p in self.roster()["people"] if str(p["person_id"]) == str(person_id)), None)
        if person is None:
            raise StoreError(f"{person_id} is not on the roster", EXIT_USAGE)
        return ann.build_packet(submission, person)

    # --- reviews ----------------------------------------------------------------------

    def import_review(self, record: Mapping[str, Any], actor: Mapping[str, Any],
                      timestamp: str) -> Dict[str, Any]:
        sid = str(record.get("submission_id", ""))
        submissions = self.submissions()
        submission = submissions.get(sid)
        if submission is None:
            raise StoreError(f"{sid} is not a recorded submission")
        reviewer = record.get("reviewer") or {}
        packet = self.packet_for(sid, str(reviewer.get("person_id")))
        errs = ann.validate_record(record, packet)
        if errs:
            raise StoreError(f"{sid}: review record invalid ({len(errs)} problem(s)): " + "; ".join(errs),
                             EXIT_SCHEMA)
        if same_person(reviewer, submission.get("author") or {}):
            raise StoreError(f"{sid}: the author of a sample cannot review it", EXIT_SCHEMA)
        allowed = assigned_to(self.assignment(), sid)
        if allowed and str(reviewer.get("person_id")) not in allowed:
            raise StoreError(f"{sid}: {reviewer.get('person_id')} is not assigned to this sample", EXIT_USAGE)
        existing = self.reviews(sid)
        if duplicate_reviewer(existing, record):
            raise StoreError(f"{sid}: this reviewer has already recorded a review of this text; "
                             "a review is never overwritten", EXIT_USAGE)
        rid = append(self.ledger("reviews"), "review", record)
        _write_json(self.path("records", f"{sid}--{reviewer.get('person_id')}.json"), record)

        now = self.reviews(sid)
        comparison = compare_reviews(now)
        state = self.state_of(sid)
        if state in ("assigned", "under_review", "needs_adjudication"):
            if len(now) < REVIEWS_PER_SAMPLE:
                if state != "under_review":
                    self.move(sid, "under_review", actor, f"review {len(now)} of {REVIEWS_PER_SAMPLE} recorded",
                              {"record_sha256": record["record_sha256"]}, timestamp)
            elif comparison["conflicts"]:
                if state != "under_review":
                    self.move(sid, "under_review", actor, "required reviews recorded; comparing",
                              {"record_sha256": record["record_sha256"]}, timestamp)
                self.move(sid, "conflicted", actor,
                          f"reviewers disagree on {len(comparison['conflicts'])} field(s)", comparison, timestamp)
            else:
                if state != "under_review":
                    self.move(sid, "under_review", actor, "required reviews recorded; comparing",
                              {"record_sha256": record["record_sha256"]}, timestamp)
                self.move(sid, "review_complete", actor,
                          f"{len(now)} independent reviews agree", comparison, timestamp)
        return {"submission_id": sid, "record_id": rid, "state": self.state_of(sid), "comparison": comparison}

    # --- adjudication -----------------------------------------------------------------

    def adjudication_packet(self, submission_id: str) -> Dict[str, Any]:
        sid = str(submission_id)
        submission = self.submissions().get(sid)
        if submission is None:
            raise StoreError(f"{sid} is not a recorded submission")
        reviews = self.reviews(sid)
        if len(reviews) < 2:
            raise StoreError(f"{sid} has fewer than two reviews; there is nothing to adjudicate",
                             EXIT_ADJUDICATION)
        return adj.packet(submission, reviews, compare_reviews(reviews))

    def import_adjudication(self, record: Mapping[str, Any], actor: Mapping[str, Any],
                            timestamp: str) -> Dict[str, Any]:
        sid = str(record.get("submission_id", ""))
        submission = self.submissions().get(sid)
        if submission is None:
            raise StoreError(f"{sid} is not a recorded submission")
        try:
            reviews = self.reviews(sid)
        except LedgerError as exc:
            raise StoreError(f"{sid}: the review ledger does not verify, so it cannot be adjudicated: {exc}",
                             EXIT_LEDGER) from None
        errs = adj.validate_record(record, submission, reviews)
        if errs:
            raise StoreError(f"{sid}: adjudication invalid ({len(errs)} problem(s)): " + "; ".join(errs),
                             EXIT_ADJUDICATION)
        state = self.state_of(sid)
        if state == "conflicted":
            self.move(sid, "needs_adjudication", actor, "conflict routed to an adjudicator",
                      {"record_sha256": record["record_sha256"]}, timestamp)
            state = self.state_of(sid)
        if state != "needs_adjudication":
            raise StoreError(f"{sid} is {state}, not awaiting adjudication", EXIT_ADJUDICATION)
        rid = append(self.ledger("adjudications"), "adjudication", record)
        _write_json(self.path("adjudication", f"{sid}.json"), record)
        blockers = adj.eligible_after_adjudication(record, reviews)
        if blockers:
            self.move(sid, "under_review", actor,
                      "adjudicated; still blocked: " + "; ".join(blockers)[:120], record, timestamp)
        else:
            self.move(sid, "review_complete", actor, "conflict adjudicated and resolved", record, timestamp)
        return {"submission_id": sid, "record_id": rid, "state": self.state_of(sid), "blockers": blockers}

    # --- derived outcome --------------------------------------------------------------

    def outcome(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """The agreed human outcome for one sample, or None when there is not one.

        An adjudication, when present and resolved, supersedes the reviews.
        Otherwise every review must agree. No other rule produces a label, and
        nothing here breaks a tie.
        """
        sid = str(submission_id)
        reviews = self.reviews(sid)
        decided = [a for a in self.adjudications(sid)]
        if decided:
            record = decided[-1]
            if adj.eligible_after_adjudication(record, reviews):
                return None
            return {"labels": record["labels"], "routing": record["routing"],
                    "expected_evidence": record["expected_evidence"],
                    "expected_abstention": record["expected_abstention"],
                    "source": "adjudication", "reviews": len(reviews),
                    "record_sha256": record["record_sha256"]}
        if len(reviews) < REVIEWS_PER_SAMPLE:
            return None
        comparison = compare_reviews(reviews)
        if comparison["conflicts"]:
            return None
        first = reviews[0]
        return {"labels": first["labels"], "routing": first["routing"],
                "expected_evidence": first["expected_evidence"],
                "expected_abstention": first["expected_abstention"],
                "source": "reviews", "reviews": len(reviews),
                "record_sha256": first["record_sha256"]}

    # --- eligibility ------------------------------------------------------------------

    def eligibility(self, index: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Why each submission is or is not eligible. Ids and reason classes only."""
        index = index if index is not None else lk.build_index()
        current = self.current_states()
        submissions = self.submissions()
        rows: Dict[str, Any] = {}
        for sid, submission in sorted(submissions.items()):
            reasons: List[str] = []
            state = current.get(sid, "submitted")
            report = self.screen(submission, index)
            if report["schema_errors"]:
                reasons.append("schema_invalid")
            if not lk.submission_hash_matches(submission):
                reasons.append("content_hash_mismatch")
            if report["leakage_severity"] == "block":
                reasons.append("exposed_corpus_overlap")
            ancestry = lk.declared_lineage_chain(submission, submissions)
            if any(a in lk.exposed_ids(index) for a in ancestry):
                reasons.append("derived_from_exposed_sample")
            if report["pii"] and not self._flag_cleared(sid, "pii_review_required"):
                reasons.append("pii_review_open")
            if report["leakage_severity"] == "warn" and not self._flag_cleared(sid, "contamination_review_required"):
                reasons.append("contamination_review_open")

            reviews = self.reviews(sid)
            if len(reviews) < REVIEWS_PER_SAMPLE:
                reasons.append("missing_human_review")
            if len({str(r["reviewer"]["person_id"]) for r in reviews}) < REVIEWS_PER_SAMPLE:
                reasons.append("reviews_not_from_distinct_humans")
            author = submission.get("author") or {}
            if any(same_person(r["reviewer"], author) for r in reviews):
                reasons.append("author_reviewed_own_sample")
            if any(not competent_for(r["reviewer"], submission["language"]) for r in reviews):
                reasons.append("reviewer_language_competency")
            comparison = compare_reviews(reviews) if len(reviews) >= 2 else {"conflicts": [], "copied_reasoning": []}
            if comparison.get("conflicts") and not self.adjudications(sid):
                reasons.append("unresolved_conflict")

            outcome = self.outcome(sid)
            if outcome is None:
                reasons.append("no_agreed_outcome")
            else:
                critical = any(bool(outcome["labels"].get(c)) for c in CRITICAL_CATEGORIES) \
                    or outcome["routing"] == "Critical"
                if critical and critical_support(reviews, outcome) < CRITICAL_AGREEMENT:
                    reasons.append("critical_needs_two_agreeing_reviewers")
            if state in ("rejected", "schema_invalid", "contaminated_after_evaluation"):
                reasons.append(f"state_{state}")
            if state not in ("review_complete", "eligible", "frozen", "evaluated"):
                reasons.append(f"state_{state}")
            rows[sid] = {
                "state": state,
                "language": submission.get("language"),
                "reviews": len(reviews),
                "pii_flags": len(report["pii"]),
                "leakage": report["leakage_severity"],
                "copied_reasoning_flags": len(comparison.get("copied_reasoning") or []),
                "eligible": not reasons,
                "reasons": sorted(set(reasons)),
            }
        return {"corpus_version": self.version, "submissions": len(rows),
                "eligible": sorted(k for k, v in rows.items() if v["eligible"]),
                "rows": rows, "heads": self.heads()}

    def _flag_cleared(self, submission_id: str, flag_state: str) -> bool:
        """True when a human moved this sample OUT of a flag state with a reason."""
        return any(t["prior_state"] == flag_state and t["new_state"] not in ("rejected",)
                   for t in self.transitions(submission_id))

    # --- coverage ---------------------------------------------------------------------

    def coverage_items(self, ids: Sequence[str]) -> List[Dict[str, Any]]:
        """Coverage rows for the named samples. Labels come from the human outcome."""
        submissions = self.submissions()
        items: List[Dict[str, Any]] = []
        for sid in ids:
            submission = submissions[sid]
            outcome = self.outcome(sid)
            if outcome is None:
                continue
            flagged = {f for r in self.reviews(sid) for f in (r.get("ambiguity_flags") or [])}
            slices = list(submission.get("intended_slices") or [])
            if "slice_declaration_looks_wrong" in flagged:
                slices = []  # a reviewer challenged the declaration; it stops counting
            items.append({"submission_id": sid, "language": submission["language"],
                          "categories": categories_of(outcome["labels"], outcome["routing"],
                                                      bool(outcome["expected_abstention"])),
                          "slices": slices})
        return items

    def coverage_report(self, ids: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        ids = list(ids) if ids is not None else self.eligibility()["eligible"]
        return coverage(self.plan(), self.coverage_items(ids))

    # --- status -----------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Machine-readable status. Counts, states, hashes; no scenario text."""
        try:
            eligibility = self.eligibility()
        except LedgerError as exc:
            raise StoreError(f"a ledger does not verify: {exc}", EXIT_LEDGER) from None
        by_state: Dict[str, int] = {}
        for row in eligibility["rows"].values():
            by_state[row["state"]] = by_state.get(row["state"], 0) + 1
        frozen = self.frozen_manifest()
        return {
            "corpus_version": self.version,
            "submissions": eligibility["submissions"],
            "by_state": dict(sorted(by_state.items())),
            "eligible": len(eligibility["eligible"]),
            "reviews": len(self.reviews()),
            "adjudications": len(self.adjudications()),
            "ledger_heads": eligibility["heads"],
            "coverage": self.coverage_report(eligibility["eligible"]) if eligibility["eligible"]
            else {"samples": 0, "satisfied": False,
                  "shortfalls": [{"kind": "total", "name": "total", "have": 0,
                                  "need": self.plan()["total_min"]}]},
            "frozen": bool(frozen),
            "frozen_manifest": {k: frozen[k] for k in ("corpus_version", "frozen_at", "corpus_sha256")}
            if frozen else None,
            "rows": eligibility["rows"],
        }

    # --- freeze artefacts -------------------------------------------------------------

    def frozen_manifest(self) -> Optional[Dict[str, Any]]:
        path = self.path("frozen", "freeze_manifest.json")
        if not path.is_file():
            return None
        return _read_json(path)

    def predictions_recorded(self) -> bool:
        """True once any evaluation output exists for this version."""
        reports = self.path("reports")
        if not reports.is_dir():
            return False
        return any(p.name.startswith("evaluation-") for p in reports.iterdir())

    def write_frozen(self, artefacts: Mapping[str, Any]) -> Dict[str, Path]:
        out: Dict[str, Path] = {}
        for name, payload in artefacts.items():
            out[name] = _write_json(self.path("frozen", f"{name}.json"), payload)
        return out

    def read_frozen(self, name: str) -> Any:
        return _read_json(self.path("frozen", f"{name}.json"))


def load_record(path: str) -> Dict[str, Any]:
    """Read one JSON record from a path the operator gave. Never printed back."""
    data = _read_json(Path(path))
    if not isinstance(data, dict):
        raise StoreError("a record file must contain one JSON object", EXIT_SCHEMA)
    return data


__all__ = ["Store", "StoreError", "RootError", "LedgerError", "load_record"]
