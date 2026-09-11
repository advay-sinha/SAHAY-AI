"""The reviewer roster, deterministic assignment, and conflict detection. Stdlib only.

Assignment is a pure function of the submissions and the roster. The same
inputs always produce the same allocation, so an assignment can be re-derived
and audited later without a stored random seed and without anyone being able
to quietly re-roll an allocation they did not like.

Rules the allocator enforces
  * A sample is never assigned to its own author, by ``person_id`` or by
    account name. One human with two accounts is still one human.
  * Two distinct people per sample. Criticality is unknown before annotation —
    that is the whole point of blinding — so every sample gets two independent
    reviews, and the repository's two-reviewer requirement for crisis and
    immediate-danger labels binds when such a label actually appears.
  * A reviewer must be recorded as competent in the sample's language, with
    Hinglish requiring declared Hindi-English code-switching competence.
  * Load is spread deterministically: a per-submission rotation derived from
    the submission id, then the least-loaded eligible person first.
  * No one is assigned the same sample twice, and the same person cannot hold
    two slots on one sample under two identities.

What it does not do
  It never invents a person, never relaxes a competency, and never reduces two
  reviewers to one because the roster is short. A roster that cannot staff the
  corpus produces a *shortfall*, which is a staffing blocker to report, not a
  policy to weaken.
"""

import hashlib
from typing import Any, Dict, List, Mapping, Sequence

from . import normalize as nz
from .annotation import critical_view, decision_view
from .identity import competent_for, normal_account, validate_person
from .plan import LANGUAGES

ROSTER_VERSION = "1.0.0"
ASSIGNMENT_VERSION = "1.0.0"

#: Reviews requested per sample. Two, always: see the module docstring.
REVIEWS_PER_SAMPLE = 2
#: Distinct reviewers whose critical labels must agree before a critical
#: sample is eligible. Mirrors ml/eval/schema.py::required_reviews.
CRITICAL_AGREEMENT = 2

ROSTER_PERSON_FIELDS = {"person_id", "identity", "kind", "role", "languages", "code_switch_competent",
                        "can_author", "can_review", "can_adjudicate"}


class AssignmentError(Exception):
    """The roster is unusable or an assignment is impossible."""


# --- roster ---------------------------------------------------------------------------


def roster_template() -> Dict[str, Any]:
    """A BLANK roster. No person is invented; the list is empty on purpose."""
    return {"roster_version": ROSTER_VERSION, "corpus_version": "", "people": []}


def validate_roster(roster: Mapping[str, Any], corpus_version: str = "") -> List[str]:
    errs: List[str] = []
    if not isinstance(roster, Mapping):
        return ["roster must be a JSON object"]
    if set(roster) != {"roster_version", "corpus_version", "people"}:
        errs.append("roster fields must be exactly roster_version, corpus_version, people")
        return errs
    if roster["roster_version"] != ROSTER_VERSION:
        errs.append(f"roster_version must be {ROSTER_VERSION}")
    if corpus_version and roster["corpus_version"] != corpus_version:
        errs.append(f"roster corpus_version must be {corpus_version!r}")
    people = roster["people"]
    if not isinstance(people, list) or not people:
        return errs + ["roster: people must be a non-empty list of real humans"]

    accounts: Dict[str, int] = {}
    for i, person in enumerate(people):
        where = f"roster[{i}]"
        if not isinstance(person, Mapping) or set(person) != ROSTER_PERSON_FIELDS:
            errs.append(f"{where}: fields must be exactly {sorted(ROSTER_PERSON_FIELDS)}")
            continue
        core = {k: person[k] for k in person if k not in ("can_author", "can_review", "can_adjudicate")}
        errs.extend(validate_person(core, where))
        for flag in ("can_author", "can_review", "can_adjudicate"):
            if not isinstance(person[flag], bool):
                errs.append(f"{where}: {flag} must be a bool")
        account = normal_account(person["identity"]).casefold()
        if account in accounts:
            errs.append(f"{where}: account already used by roster[{accounts[account]}]")
        accounts[account] = i
    return errs


def people_by_person_id(roster: Mapping[str, Any]) -> Dict[str, List[Mapping[str, Any]]]:
    """Roster entries grouped by human. Several accounts may map to one human."""
    out: Dict[str, List[Mapping[str, Any]]] = {}
    for person in roster.get("people", []):
        out.setdefault(str(person.get("person_id")), []).append(person)
    return out


def staffing(roster: Mapping[str, Any]) -> Dict[str, Any]:
    """Who the roster can actually staff, per language and per capability."""
    humans = people_by_person_id(roster)
    report: Dict[str, Any] = {"humans": len(humans), "accounts": len(roster.get("people", []))}
    for capability in ("can_author", "can_review", "can_adjudicate"):
        report[capability] = sorted({pid for pid, entries in humans.items()
                                     if any(e.get(capability) for e in entries)})
    for lang in LANGUAGES:
        report[f"reviewers_{lang}"] = sorted({
            pid for pid, entries in humans.items()
            if any(e.get("can_review") and competent_for(e, lang) for e in entries)})
    return report


# --- assignment -----------------------------------------------------------------------


def _rotation(submission_id: str, size: int) -> int:
    if size <= 0:
        return 0
    return int(hashlib.sha256(str(submission_id).encode("utf-8")).hexdigest(), 16) % size


def _eligible(roster: Mapping[str, Any], submission: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """One entry per eligible human, deterministically chosen and ordered."""
    author = submission.get("author") or {}
    language = submission.get("language")
    chosen: Dict[str, Mapping[str, Any]] = {}
    for person in roster.get("people", []):
        if not person.get("can_review") or not competent_for(person, language):
            continue
        pid = str(person.get("person_id"))
        if pid == str(author.get("person_id")):
            continue
        if normal_account(person.get("identity")).casefold() == normal_account(author.get("identity")).casefold():
            continue
        account = normal_account(person.get("identity")).casefold()
        best = chosen.get(pid)
        if best is None or account < normal_account(best.get("identity")).casefold():
            chosen[pid] = person  # one slot per human, the lowest account name breaks ties
    return [chosen[pid] for pid in sorted(chosen)]


def assign(submissions: Sequence[Mapping[str, Any]], roster: Mapping[str, Any],
           reviews_per_sample: int = REVIEWS_PER_SAMPLE) -> Dict[str, Any]:
    """Deterministically allocate reviewers. Pure: same inputs, same output."""
    load: Dict[str, int] = {str(p.get("person_id")): 0 for p in roster.get("people", [])}
    rows: List[Dict[str, Any]] = []
    shortfalls: List[Dict[str, Any]] = []
    for submission in sorted(submissions, key=lambda s: str(s.get("submission_id"))):
        sid = str(submission.get("submission_id"))
        pool = _eligible(roster, submission)
        if len(pool) < reviews_per_sample:
            shortfalls.append({"submission_id": sid, "language": submission.get("language"),
                               "eligible": len(pool), "needed": reviews_per_sample,
                               "reason": "not enough independent, language-competent reviewers"})
        offset = _rotation(sid, len(pool)) if pool else 0
        rotated = [(i, pool[(offset + i) % len(pool)]) for i in range(len(pool))] if pool else []
        rotated.sort(key=lambda pair: (load[str(pair[1]["person_id"])], pair[0]))
        picked = [person for _, person in rotated[:reviews_per_sample]]
        for person in picked:
            load[str(person["person_id"])] += 1
        rows.append({
            "submission_id": sid,
            "language": submission.get("language"),
            "reviewers": [{"person_id": str(p["person_id"]), "identity": normal_account(p["identity"])}
                          for p in picked],
            "requested": reviews_per_sample,
            "assigned": len(picked),
        })
    return {"assignment_version": ASSIGNMENT_VERSION,
            "corpus_version": roster.get("corpus_version"),
            "reviews_per_sample": reviews_per_sample,
            "assignments": rows,
            "load": dict(sorted(load.items())),
            "shortfalls": shortfalls,
            "complete": not shortfalls}


def assigned_to(assignment: Mapping[str, Any], submission_id: str) -> List[str]:
    for row in assignment.get("assignments", []):
        if row["submission_id"] == str(submission_id):
            return [r["person_id"] for r in row["reviewers"]]
    return []


# --- conflicts ------------------------------------------------------------------------


def duplicate_reviewer(records: Sequence[Mapping[str, Any]], new_record: Mapping[str, Any]) -> bool:
    """True if this human already recorded a review of this exact narrative."""
    pid = str((new_record.get("reviewer") or {}).get("person_id"))
    account = normal_account((new_record.get("reviewer") or {}).get("identity")).casefold()
    narrative = new_record.get("narrative_sha256")
    for r in records:
        if r.get("submission_id") != new_record.get("submission_id"):
            continue
        if r.get("narrative_sha256") != narrative:
            continue
        other = r.get("reviewer") or {}
        if str(other.get("person_id")) == pid or normal_account(other.get("identity")).casefold() == account:
            return True
    return False


def copied_reasoning(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """Pairs of reviewers whose reasoning is identical after normalisation.

    A REVIEW FLAG, nothing more. Identical text can mean a copy-paste, a shared
    template, a very short sentence, or two people reaching the same conclusion
    in the same words. It never proves collusion and never invalidates a record
    on its own: a human decides what it means.
    """
    out: List[Dict[str, str]] = []
    seen: Dict[str, Mapping[str, Any]] = {}
    for r in sorted(records, key=lambda x: str((x.get("reviewer") or {}).get("person_id"))):
        key = nz.compare(str(r.get("reasoning", "")))
        if not key:
            continue
        first = seen.get(key)
        if first is not None and str((first.get("reviewer") or {}).get("person_id")) != \
                str((r.get("reviewer") or {}).get("person_id")):
            out.append({"submission_id": str(r.get("submission_id")),
                        "reviewer_a": str((first.get("reviewer") or {}).get("person_id")),
                        "reviewer_b": str((r.get("reviewer") or {}).get("person_id")),
                        "note": "identical reasoning after normalisation; a flag for human inspection only"})
        else:
            seen.setdefault(key, r)
    return out


def compare_reviews(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """What two or more reviewers of one sample agree and disagree on."""
    if len(records) < 2:
        return {"reviews": len(records), "conflicts": [], "critical_conflict": False,
                "agreed": False, "copied_reasoning": []}
    views = [decision_view(r) for r in records]
    conflicts: List[str] = []
    base = views[0]
    for field in ("routing", "expected_abstention", "decision"):
        if any(v[field] != base[field] for v in views[1:]):
            conflicts.append(field)
    for category in sorted(base["labels"]):
        if any(v["labels"].get(category) != base["labels"].get(category) for v in views[1:]):
            conflicts.append(f"label:{category}")
    if any(v["expected_evidence"] != base["expected_evidence"] for v in views[1:]):
        conflicts.append("expected_evidence")
    crit = [critical_view(r) for r in records]
    critical_conflict = any(c != crit[0] for c in crit[1:])
    return {"reviews": len(records), "conflicts": sorted(set(conflicts)),
            "critical_conflict": critical_conflict, "agreed": not conflicts,
            "copied_reasoning": copied_reasoning(records)}


def critical_support(records: Sequence[Mapping[str, Any]], decision: Mapping[str, Any]) -> int:
    """How many distinct humans recorded the same critical view as ``decision``.

    ``decision`` may be a review record or an adjudication decision; both carry
    ``labels`` and ``routing``. Used by the freeze gate to check that a critical
    label rests on two independent human reviews and not on one adjudicator.
    """
    want = critical_view(decision)
    return len({str((r.get("reviewer") or {}).get("person_id")) for r in records if critical_view(r) == want})
