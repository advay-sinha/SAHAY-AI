"""The author-submission schema, its content hash and the PII screen. Stdlib only.

A submission is one fictional scenario written by one named human. This module
defines what a submission IS, validates it, hashes it and screens it for
things that look like personal information. It never writes one, never fills a
field and never invents an attestation.

Blank templates for human authors come from ``template()``; the CLI writes one
into ``<root>/intake/`` on ``init``. Every string field in a template is empty,
and validation refuses an empty field, so an unedited template cannot be
imported.

The content hash
  ``content_sha256`` covers only what a reviewer is allowed to see: the id, the
  corpus version, the language, the script, the turns, the declared slices and
  the lineage. It deliberately excludes the author identity, the timestamp and
  the attestations, so a blinded reviewer can recompute the hash from their
  packet and prove they annotated the exact text the author submitted, without
  learning who wrote it. The whole record, author included, is hashed again by
  the ledger as ``record_id``.

The PII screen
  ``personal_information()`` reports pattern *names* and turn ids, never the
  matched text, and it is a screen for human inspection — not a guarantee. It
  finds shapes: digit strings, e-mail and URL shapes, handles, identifier
  keywords, self-introduction phrasing. It cannot recognise an ordinary
  personal name, a real village, a real date of an incident, or a narrative
  that a survivor would recognise as their own. Those are the reasons a human
  must read every submission before it becomes eligible, and the reason the
  attestations exist.
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Mapping, Tuple

from ..schema import IDENTIFYING_PATTERNS, SPEAKERS
from .identity import validate_person
from .plan import LANGUAGES, SCRIPTS, SLICE_NAMES

RECORD_VERSION = "1.0.0"

#: Relations that make a submission DERIVED from another sample. Same vocabulary
#: as ml.eval.contamination.DERIVATION_RELATIONS, re-stated so that this module
#: does not have to import a registry to validate a shape.
DERIVATION_RELATIONS = ("translation", "back_translation", "transliteration", "paraphrase", "excerpt", "augmentation")

RECORD_FIELDS = {"record_version", "submission_id", "corpus_version", "language", "script", "author",
                 "created_at", "turns", "intended_slices", "derived", "translated", "lineage",
                 "attestations", "content_sha256"}
#: Fields the content hash is computed over, in this order-independent set.
CONTENT_FIELDS = ("submission_id", "corpus_version", "language", "script", "turns",
                  "intended_slices", "derived", "translated", "lineage")
#: The subset a blinded reviewer is shown, and can therefore re-hash themself.
#: Declared slices and lineage are excluded from a packet because they hint at
#: the answer, so the reviewer verifies this narrower hash instead.
NARRATIVE_FIELDS = ("submission_id", "corpus_version", "language", "script", "turns")

#: Exact sentences an author must copy. An altered sentence is refused, so
#: "I agree" or a paraphrase cannot stand in for an attestation.
ATTESTATIONS: Dict[str, str] = {
    "fictional":
        "This scenario is entirely fictional and I invented it myself.",
    "no_real_victim_narrative":
        "This scenario is not the account of any real person and is not based on a specific real case.",
    "no_identifying_information":
        "This scenario contains no real name, contact detail, address, case number, account or other "
        "identifying information.",
    "no_llm_authoring_or_translation":
        "No language model or other automated system wrote, translated or rewrote any part of this scenario.",
    "no_predictions_viewed":
        "I have not seen this system's detector output, score, band, routing or evaluation results for this "
        "scenario or for any scenario like it.",
    "own_work":
        "I am a human author, I wrote this submission myself, and I understand that I may not review or "
        "approve it.",
}

LANG_CODE = {"en": "EN", "hi": "HI", "hinglish": "HG"}
#: Which scripts each language may be written in (mirrors coverage_plan_v1.json).
LANG_SCRIPTS = {"en": ("latin",), "hi": ("devanagari",), "hinglish": ("latin", "mixed")}

_SUBMISSION_ID = re.compile(r"^SUB-([0-9A-Z]+)-(EN|HI|HG)-([0-9]{4})$")
_TURN_ID = re.compile(r"^t[0-9]+$")
_STATE = re.compile(r"^S(?:[0-9]|1[01]|X)$")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")

#: Additional shapes on top of ml.eval.schema.IDENTIFYING_PATTERNS. Names only
#: are ever reported; the matched text is never printed or logged.
EXTRA_PII_PATTERNS = {
    "social_handle": re.compile(r"(?<![\w@])@[A-Za-z0-9._]{3,}"),
    "self_introduction": re.compile(r"\b(my name is|i am called|mera naam|मेरा "
                                    r"नाम)\b", re.IGNORECASE),
    "identifier_keyword": re.compile(r"\b(aadhaar|aadhar|आधार|pan\s*card|voter\s*id|"
                                     r"ration\s*card|case\s*(no\.?|number)|diary\s*(no\.?|number)|"
                                     r"cnr|acknowledgement\s*(no\.?|number))\b", re.IGNORECASE),
    "account_shape": re.compile(r"\b[A-Z]{2,5}\d{4,}\b"),
    "date_of_incident": re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-](19|20)\d{2}\b"),
}

MIN_TURN_CHARS = 8
MAX_TURNS = 12


class SubmissionError(Exception):
    """A submission is malformed, unhashable or refuses to validate."""


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_sha256(submission: Mapping[str, Any]) -> str:
    """Hash of the fields a blinded reviewer can see. Missing field -> error."""
    try:
        payload = {k: submission[k] for k in CONTENT_FIELDS}
    except KeyError as exc:
        raise SubmissionError(f"cannot hash a submission without {exc.args[0]}") from None
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def narrative_sha256(source: Mapping[str, Any]) -> str:
    """Hash of exactly what a blinded reviewer sees. Works on a submission or a packet."""
    try:
        payload = {k: source[k] for k in NARRATIVE_FIELDS}
    except KeyError as exc:
        raise SubmissionError(f"cannot hash a narrative without {exc.args[0]}") from None
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def version_token(corpus_version: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(corpus_version)).upper()


def template(corpus_version: str = "v1", language: str = "en") -> Dict[str, Any]:
    """A BLANK submission for a human author. Every content field is empty."""
    return {
        "record_version": RECORD_VERSION,
        "submission_id": f"SUB-{version_token(corpus_version)}-{LANG_CODE.get(language, 'EN')}-0000",
        "corpus_version": corpus_version,
        "language": language,
        "script": LANG_SCRIPTS.get(language, ("latin",))[0],
        "author": {"person_id": "", "identity": "", "kind": "human", "role": "",
                   "languages": [], "code_switch_competent": False},
        "created_at": "",
        "turns": [{"id": "t1", "speaker": "victim", "state": "S1", "text": ""}],
        "intended_slices": [],
        "derived": False,
        "translated": False,
        "lineage": None,
        "attestations": {key: "" for key in sorted(ATTESTATIONS)},
        "content_sha256": "",
    }


def validate(submission: Mapping[str, Any], corpus_version: str = "") -> List[str]:
    """Every problem with one submission. Empty means schema-valid.

    Messages name fields, ids and pattern classes. None quotes scenario text.
    """
    errs: List[str] = []
    if not isinstance(submission, Mapping):
        return ["submission must be a JSON object"]
    extra = set(submission) - RECORD_FIELDS
    missing = RECORD_FIELDS - set(submission)
    if extra:
        errs.append(f"unknown fields {sorted(extra)}")
    if missing:
        return errs + [f"missing fields {sorted(missing)}"]

    if submission["record_version"] != RECORD_VERSION:
        errs.append(f"record_version must be {RECORD_VERSION}")
    if corpus_version and submission["corpus_version"] != corpus_version:
        errs.append(f"corpus_version must be {corpus_version!r} for this root")

    language = submission["language"]
    script = submission["script"]
    if language not in LANGUAGES:
        errs.append(f"language must be one of {LANGUAGES}")
    if script not in SCRIPTS:
        errs.append(f"script must be one of {SCRIPTS}")
    if language in LANG_SCRIPTS and script not in LANG_SCRIPTS[language]:
        errs.append(f"language {language} may only be written in {LANG_SCRIPTS[language]}")

    sid = str(submission["submission_id"])
    m = _SUBMISSION_ID.match(sid)
    if not m:
        errs.append("submission_id must look like SUB-V1-EN-0001")
    else:
        token, code, number = m.groups()
        if token != version_token(submission["corpus_version"]):
            errs.append("submission_id version segment does not match corpus_version")
        if language in LANG_CODE and code != LANG_CODE[language]:
            errs.append(f"submission_id language code {code} does not match language {language}")
        if number == "0000":
            errs.append("submission_id 0000 is the template placeholder")

    errs.extend(validate_person(submission["author"], "author"))

    created = str(submission["created_at"])
    try:
        ts = datetime.fromisoformat(created)
        if ts.tzinfo is None:
            errs.append("created_at needs a timezone offset")
    except ValueError:
        errs.append("created_at must be ISO 8601 with a timezone")

    turns = submission["turns"]
    if not isinstance(turns, list) or not turns:
        errs.append("turns must be a non-empty list")
        turns = []
    if len(turns) > MAX_TURNS:
        errs.append(f"at most {MAX_TURNS} turns")
    ids: List[str] = []
    victim_turns = 0
    for t in turns:
        if not isinstance(t, Mapping) or set(t) != {"id", "speaker", "state", "text"}:
            errs.append("each turn needs exactly id, speaker, state, text")
            continue
        if not _TURN_ID.match(str(t["id"])):
            errs.append("turn ids must look like t1")
        ids.append(str(t["id"]))
        if t["speaker"] not in SPEAKERS:
            errs.append(f"turn {t['id']}: speaker must be one of {SPEAKERS}")
        if not _STATE.match(str(t["state"])):
            errs.append(f"turn {t['id']}: state must be S0-S11 or SX")
        text = str(t["text"])
        if len(text.strip()) < MIN_TURN_CHARS:
            errs.append(f"turn {t['id']}: text is empty or too short to annotate")
        if t["speaker"] == "victim":
            victim_turns += 1
        if language == "hi" and not _DEVANAGARI.search(text):
            errs.append(f"turn {t['id']}: a Hindi sample must be written in Devanagari")
        if language == "hi" and _LATIN.search(text) and script == "devanagari":
            errs.append(f"turn {t['id']}: Latin text in a devanagari-script sample; declare script 'mixed' "
                        "and language 'hinglish' instead")
        if language in ("en", "hinglish") and script == "latin" and _DEVANAGARI.search(text):
            errs.append(f"turn {t['id']}: Devanagari in a latin-script sample; declare script 'mixed'")
    if ids and len(set(ids)) != len(ids):
        errs.append("duplicate turn ids")
    if ids and ids != sorted(ids, key=lambda i: int(i[1:])):
        errs.append("turns must be in ascending turn-id order")
    if turns and not victim_turns:
        errs.append("at least one victim turn is required")

    slices = submission["intended_slices"]
    if not isinstance(slices, list) or not slices:
        errs.append("intended_slices must name at least one challenge slice")
    else:
        for s in slices:
            if s not in SLICE_NAMES:
                errs.append(f"unknown challenge slice {s!r}")
        if len(set(slices)) != len(slices):
            errs.append("duplicate challenge slice")
    if isinstance(slices, list) and "multi_turn_evidence" in slices and len(turns) < 2:
        errs.append("multi_turn_evidence needs more than one turn")
    if isinstance(slices, list) and "later_turn_evidence" in slices and victim_turns < 2:
        errs.append("later_turn_evidence needs more than one victim turn")

    for flag in ("derived", "translated"):
        if not isinstance(submission[flag], bool):
            errs.append(f"{flag} must be a bool")
    lineage = submission["lineage"]
    derived = bool(submission["derived"]) or bool(submission["translated"])
    if derived and not isinstance(lineage, Mapping):
        errs.append("a derived or translated submission must carry lineage {parent_id, relation}")
    elif lineage is not None:
        if not isinstance(lineage, Mapping) or set(lineage) != {"parent_id", "relation"}:
            errs.append("lineage fields must be exactly parent_id and relation")
        else:
            if not str(lineage["parent_id"]).strip():
                errs.append("lineage needs parent_id")
            if lineage["relation"] not in DERIVATION_RELATIONS:
                errs.append(f"lineage relation must be one of {DERIVATION_RELATIONS}")
            if not derived:
                errs.append("lineage is present but neither derived nor translated is true")

    att = submission["attestations"]
    if not isinstance(att, Mapping) or set(att) != set(ATTESTATIONS):
        errs.append(f"attestations must be exactly {sorted(ATTESTATIONS)}")
    else:
        for key, sentence in sorted(ATTESTATIONS.items()):
            if str(att[key]).strip() != sentence:
                errs.append(f"attestation {key!r} is missing or altered; it must be copied exactly")

    if not errs or all(not e.startswith(("missing fields", "cannot hash")) for e in errs):
        try:
            want = content_sha256(submission)
        except SubmissionError as exc:
            errs.append(str(exc))
        else:
            if str(submission["content_sha256"]) != want:
                errs.append("content_sha256 does not match the submission content")
    return errs


def personal_information(submission: Mapping[str, Any]) -> List[Dict[str, str]]:
    """Possible personal information, as ``{turn, pattern}`` pairs.

    A screen for human inspection. It never returns the matched text, and it
    makes no claim to be complete: ordinary personal names, place names and
    real incident details are invisible to it.
    """
    hits: List[Dict[str, str]] = []
    patterns: List[Tuple[str, Any]] = sorted(IDENTIFYING_PATTERNS.items()) + sorted(EXTRA_PII_PATTERNS.items())
    for t in submission.get("turns") or []:
        if not isinstance(t, Mapping):
            continue
        text = str(t.get("text", ""))
        for name, pattern in patterns:
            if pattern.search(text):
                hits.append({"turn": str(t.get("id", "?")), "pattern": name})
    return hits
