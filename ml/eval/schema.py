"""SAHAY-AI ML label schema — the contract between fixtures and the evaluator.

Standard library only. This module defines what a labelled sample IS and
validates corpora against it. It does not score anything.

Schema version 1.0.0 (frozen 2026-09-11). A change to any category name, its
meaning or the sample shape bumps the version; old corpora keep validating
against the version they declare.

Category definitions (each is a boolean label on the WHOLE sample, with the
turn ids that carry it in `expected_evidence`):

  crisis_self_harm            The victim, speaking for themself, expresses
                              present suicidal intent, a wish to die, or
                              self-harm. Negated or quoted-only language is NOT
                              this category (see negated/quoted below).
  immediate_danger            The victim reports danger that is present or
                              imminent: attackers at the door, coming tonight,
                              a weapon now. A future threat ("they will come
                              back") is continuing_threat, not this.
  continuing_threat           A threat, intimidation or pressure (including
                              pressure to withdraw a complaint) directed at the
                              victim or family, not necessarily imminent.
  medical_urgency             Someone is injured, bleeding, unconscious or
                              needs treatment now. Mild pain alone is not.
  isolation_boycott_displacement  Social boycott, denial of water/shops/work,
                              forced to leave, nobody allowed to speak to them.
  legal_urgency               A complaint, FIR, police refusal, court or
                              hearing matter that needs action or information.
  communication_safety_coercion  The victim cannot speak freely (someone is
                              listening, phone checked) or is being coerced
                              about speaking or complaining, including pressure
                              to withdraw a complaint or to keep quiet.
  explicit_human_request      The victim asks, in words, for a person.
  negated_risk_language       Risk vocabulary appears but is explicitly negated
                              in its own clause ("I would never hurt myself").
  quoted_attributed_risk      Risk vocabulary appears only as someone else's
                              words or a report (news, film, a neighbour).
  adversarial_injection       The text tries to instruct or manipulate the
                              system (ignore instructions, set my risk low,
                              roleplay, reveal your score).

Expected outcomes (in `expected`):
  crisis_precheck    bool  — should the synchronous pre-check fire on some turn
  routed_critical    bool  — should the case be routed Critical (crisis or
                             confirmed immediate danger)
  abstain            bool | null — should the assessment return Needs Human
                             Assessment (no score); null = not specified
  band               Low|Moderate|High|Critical|null — expected SVI band when
                             one is specified; null = not specified

Review model:
  status  author_draft   written by the fixture author, unreviewed
          pending_review awaiting the required human reviews
          approved       required human reviews recorded
          rejected       reviewers rejected it; kept for the record
  A reviewer entry is {"reviewer": <GitHub username or "TODO-reviewer-N">,
  "decision": "approve"|"reject"|"pending", "date": "YYYY-MM-DD"|null}.
  Placeholders ("TODO-...") and "pending" decisions never count as approvals.

Locked set rule: a sample may be in the locked split only if it is
`approved` with at least `required_reviews` real approvals, and critical
samples (crisis_self_harm or immediate_danger positive) require two.
"""

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"
SCHEMA_NAME = "sahay-ml-labels"

LANGUAGES = ("hi", "en", "hinglish")
SPLITS = ("dev", "candidate", "locked")
CHANNELS = ("mobile_voice", "mobile_chat", "portal_chat", "upload")
SPEAKERS = ("victim", "assistant", "officer")
BANDS = ("Low", "Moderate", "High", "Critical")

#: Detector-backed categories (each has a system prediction).
DETECTOR_CATEGORIES = (
    "crisis_self_harm",
    "immediate_danger",
    "continuing_threat",
    "medical_urgency",
    "isolation_boycott_displacement",
    "legal_urgency",
    "communication_safety_coercion",
    "explicit_human_request",
)
#: Slice categories (labels describing the text, used to cut metrics).
SLICE_CATEGORIES = (
    "negated_risk_language",
    "quoted_attributed_risk",
    "adversarial_injection",
)
CATEGORIES = DETECTOR_CATEGORIES + SLICE_CATEGORIES

#: Categories whose positives need two real reviewers before locking.
CRITICAL_CATEGORIES = ("crisis_self_harm", "immediate_danger")

#: Free-form scenario tags, for coverage accounting only.
TAGS = (
    "immediate_danger", "crisis", "threat_after_complaint", "medical", "boycott_displacement",
    "coercion", "legal_question", "low_distress", "negated_crisis", "quoted_crisis",
    "human_request", "code_switch", "misspelling", "regional_variant", "weak_indicators",
    "conflicting_reassurance", "advice_seeking", "diagnosis_request", "minimising_blaming",
    "roleplay", "embedded_instruction", "prompt_injection", "multi_turn", "voice_channel",
)

REVIEW_STATUSES = ("author_draft", "pending_review", "approved", "rejected")
REVIEW_DECISIONS = ("approve", "reject", "pending")
PLACEHOLDER_REVIEWER = re.compile(r"^TODO-")

_ID = re.compile(r"^(DEV|CAND|LOCK)-(HI|EN|HG)-[A-Z0-9-]+$")
_TURN_ID = re.compile(r"^t[0-9]+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SAMPLE_KEYS = {
    "id", "schema_version", "split", "language", "channel", "tags", "turns", "labels",
    "expected_evidence", "expected", "review", "notes",
}
EXPECTED_KEYS = {"crisis_precheck", "routed_critical", "abstain", "band"}

_ID_PREFIX = {"dev": "DEV", "candidate": "CAND", "locked": "LOCK"}
_LANG_CODE = {"hi": "HI", "en": "EN", "hinglish": "HG"}


def is_critical(sample: Mapping[str, Any]) -> bool:
    labels = sample.get("labels") or {}
    return any(bool(labels.get(c)) for c in CRITICAL_CATEGORIES)


def real_approvals(sample: Mapping[str, Any]) -> int:
    """Count approvals from real reviewers. Placeholders never count."""
    review = sample.get("review") or {}
    count = 0
    seen = set()
    for r in review.get("reviewers") or []:
        name = str(r.get("reviewer") or "")
        if not name or PLACEHOLDER_REVIEWER.match(name) or name in seen:
            continue
        if r.get("decision") == "approve" and r.get("date"):
            seen.add(name)
            count += 1
    return count


def required_reviews(sample: Mapping[str, Any]) -> int:
    return 2 if is_critical(sample) else 1


def lock_eligible(sample: Mapping[str, Any]) -> bool:
    review = sample.get("review") or {}
    return review.get("status") == "approved" and real_approvals(sample) >= required_reviews(sample)


def validate_sample(sample: Mapping[str, Any]) -> List[str]:
    """Return a list of problems. Empty means the sample is valid."""
    errs: List[str] = []
    sid = str(sample.get("id", "<no id>"))

    def err(msg: str) -> None:
        errs.append(f"{sid}: {msg}")

    extra = set(sample) - SAMPLE_KEYS
    missing = SAMPLE_KEYS - set(sample)
    if extra:
        err(f"unknown keys {sorted(extra)}")
    if missing:
        err(f"missing keys {sorted(missing)}")
        return errs

    if sample["schema_version"] != SCHEMA_VERSION:
        err(f"schema_version {sample['schema_version']!r} != {SCHEMA_VERSION}")
    if sample["split"] not in SPLITS:
        err(f"split {sample['split']!r}")
    if sample["language"] not in LANGUAGES:
        err(f"language {sample['language']!r}")
    if sample["channel"] not in CHANNELS:
        err(f"channel {sample['channel']!r}")
    if not _ID.match(sid):
        err("id must look like DEV-EN-001 / CAND-HG-004 / LOCK-HI-002")
    else:
        prefix, code = sid.split("-")[:2]
        if sample["split"] in _ID_PREFIX and prefix != _ID_PREFIX[sample["split"]]:
            err(f"id prefix {prefix} does not match split {sample['split']}")
        if sample["language"] in _LANG_CODE and code != _LANG_CODE[sample["language"]]:
            err(f"id language code {code} does not match language {sample['language']}")

    for tag in sample["tags"]:
        if tag not in TAGS:
            err(f"unknown tag {tag!r}")

    turns = sample["turns"]
    if not isinstance(turns, list) or not turns:
        err("turns must be a non-empty list")
        turns = []
    turn_ids = []
    for t in turns:
        if set(t) != {"id", "speaker", "state", "text"}:
            err(f"turn keys {sorted(t)} must be id, speaker, state, text")
            continue
        if not _TURN_ID.match(str(t["id"])):
            err(f"turn id {t['id']!r}")
        if t["speaker"] not in SPEAKERS:
            err(f"turn speaker {t['speaker']!r}")
        if not str(t["text"]).strip():
            err(f"turn {t['id']} has empty text")
        turn_ids.append(t["id"])
    if len(set(turn_ids)) != len(turn_ids):
        err("duplicate turn ids")
    victim_ids = {t["id"] for t in turns if isinstance(t, Mapping) and t.get("speaker") == "victim"}
    if not victim_ids:
        err("at least one victim turn is required")

    labels = sample["labels"]
    if set(labels) != set(CATEGORIES):
        err(f"labels must have exactly {len(CATEGORIES)} categories")
    for c, v in labels.items():
        if not isinstance(v, bool):
            err(f"label {c} must be a bool")

    evidence = sample["expected_evidence"]
    for c, ids in evidence.items():
        if c not in DETECTOR_CATEGORIES:
            err(f"expected_evidence for non-detector category {c}")
            continue
        if not labels.get(c):
            err(f"expected_evidence for {c} but the label is false")
        if not ids:
            err(f"expected_evidence for {c} is empty")
        for i in ids:
            if i not in victim_ids:
                err(f"expected_evidence id {i!r} for {c} is not a victim turn")
    for c in DETECTOR_CATEGORIES:
        if labels.get(c) and c not in evidence:
            err(f"positive label {c} needs expected_evidence")

    exp = sample["expected"]
    if set(exp) != EXPECTED_KEYS:
        err(f"expected keys must be {sorted(EXPECTED_KEYS)}")
    else:
        for k in ("crisis_precheck", "routed_critical"):
            if not isinstance(exp[k], bool):
                err(f"expected.{k} must be a bool")
        if exp["abstain"] is not None and not isinstance(exp["abstain"], bool):
            err("expected.abstain must be a bool or null")
        if exp["band"] is not None and exp["band"] not in BANDS:
            err(f"expected.band {exp['band']!r}")
        if exp["abstain"] is True and exp["band"] not in (None, "Critical"):
            err("an expected abstention cannot also expect a non-Critical band")
        if labels.get("crisis_self_harm") and not exp["crisis_precheck"]:
            err("crisis_self_harm positive must expect the pre-check to fire")
        if (labels.get("crisis_self_harm") or labels.get("immediate_danger")) and not exp["routed_critical"]:
            err("a critical label must expect routed_critical")

    review = sample["review"]
    if review.get("status") not in REVIEW_STATUSES:
        err(f"review.status {review.get('status')!r}")
    if not isinstance(review.get("reviewers"), list):
        err("review.reviewers must be a list")
    else:
        for r in review["reviewers"]:
            if set(r) != {"reviewer", "decision", "date"}:
                err("reviewer entries need reviewer, decision, date")
                continue
            if r["decision"] not in REVIEW_DECISIONS:
                err(f"review decision {r['decision']!r}")
            if r["date"] is not None and not _DATE.match(str(r["date"])):
                err(f"review date {r['date']!r}")
            if PLACEHOLDER_REVIEWER.match(str(r["reviewer"])) and r["decision"] != "pending":
                err("a placeholder reviewer can only be pending")
    if review.get("status") == "approved" and real_approvals(sample) < required_reviews(sample):
        err(f"status approved with {real_approvals(sample)} real approvals; needs {required_reviews(sample)}")
    if review.get("required_reviews") != required_reviews(sample):
        err(f"review.required_reviews must be {required_reviews(sample)}")
    if sample["split"] == "locked" and not lock_eligible(sample):
        err("locked sample is not lock-eligible (needs approved status and real approvals)")
    if sample["split"] in ("candidate", "locked") and is_critical(sample) \
            and review.get("status") not in ("pending_review", "approved", "rejected"):
        err("a critical evaluation sample must be pending_review until reviewed")

    if not isinstance(sample["notes"], str):
        err("notes must be a string")
    return errs


def validate_corpus(corpus: Mapping[str, Any]) -> List[str]:
    """Validate a corpus file: {schema, schema_version, corpus_version, split, samples}."""
    errs: List[str] = []
    for key in ("schema", "schema_version", "corpus_version", "split", "description", "samples"):
        if key not in corpus:
            errs.append(f"corpus: missing {key}")
    if errs:
        return errs
    if corpus["schema"] != SCHEMA_NAME:
        errs.append(f"corpus: schema {corpus['schema']!r}")
    if corpus["schema_version"] != SCHEMA_VERSION:
        errs.append(f"corpus: schema_version {corpus['schema_version']!r}")
    ids = [s.get("id") for s in corpus["samples"]]
    if len(set(ids)) != len(ids):
        errs.append("corpus: duplicate sample ids")
    for s in corpus["samples"]:
        errs.extend(validate_sample(s))
        if s.get("split") != corpus["split"]:
            errs.append(f"{s.get('id')}: split {s.get('split')!r} in a {corpus['split']} corpus")
    return errs


def disjoint(corpora: Sequence[Mapping[str, Any]]) -> List[str]:
    """No sample id, and no identical victim text, may appear in two splits."""
    errs: List[str] = []
    seen_ids: Dict[str, str] = {}
    seen_text: Dict[str, str] = {}
    for corpus in corpora:
        for s in corpus["samples"]:
            if s["id"] in seen_ids:
                errs.append(f"{s['id']}: appears in {seen_ids[s['id']]} and {corpus['split']}")
            seen_ids[s["id"]] = corpus["split"]
            for t in s["turns"]:
                key = " ".join(str(t["text"]).casefold().split())
                if t["speaker"] != "victim":
                    continue
                other = seen_text.get(key)
                if other and other.split(":")[0] != corpus["split"]:
                    errs.append(f"{s['id']}: victim text duplicated from {other}")
                seen_text.setdefault(key, f"{corpus['split']}:{s['id']}")
    return errs


#: Patterns that must never appear in a fictional fixture.
IDENTIFYING_PATTERNS = {
    "phone": re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)"),
    "long_number": re.compile(r"(?<!\d)\d{7,}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "url": re.compile(r"https?://|www\.", re.IGNORECASE),
    "aadhaar_like": re.compile(r"(?<!\d)\d{4}\s\d{4}\s\d{4}(?!\d)"),
    "pin_code": re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)"),
    "fir_number": re.compile(r"\bFIR\s*(no\.?|number)?\s*\d+", re.IGNORECASE),
}


def identifying_data(samples: Iterable[Mapping[str, Any]]) -> List[str]:
    """Return fixture ids whose text looks like identifying data."""
    hits: List[str] = []
    for s in samples:
        blob = " ".join(str(t["text"]) for t in s["turns"]) + " " + str(s.get("notes", ""))
        for name, pattern in IDENTIFYING_PATTERNS.items():
            if pattern.search(blob):
                hits.append(f"{s['id']}:{name}")
    return hits
