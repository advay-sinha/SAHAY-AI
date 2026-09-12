"""External-corpus adapter for private, offline exploratory research. Stdlib only.

    python -m ml.data.external_corpus specs
    python -m ml.data.external_corpus convert --dataset <id>
    python -m ml.data.external_corpus convert --dataset <id> --local-research-override \\
        --acknowledge "<OVERRIDE_ACKNOWLEDGEMENT>" [--operator <name>]

Converts records from a registered external dataset into a private, normalised
research format beneath ``<SAHAY_DATASETS_ROOT>/normalized/``. The output is a
QUARANTINED RESEARCH ARTEFACT: it can never enter the SAHAY product, the demo,
a victim-facing flow, training, tuning, the locked or blind corpus, or any
official evaluation. Invariant 8 is unchanged: real or potentially real victim
narratives are never used in the MVP.

Governance, fail-closed by default
----------------------------------
Without the override, conversion runs only for a dataset whose registry state
permits research use (``governance.select_for(..., "research")``). No external
dataset is in such a state, so the default path refuses every one of them
before reading a row.

The local exploratory research override
---------------------------------------
The project owner may authorise private, local, offline exploratory research
on a ``licence_pending`` dataset. That authorisation is expressed per run,
never stored in the registry, and it bypasses exactly ONE gate: the
licence-based read gate. It never bypasses private-root confinement, privacy
screening, product/MVP/demo exclusion, training and tuning exclusion,
redistribution exclusion, locked/blind/official-evaluation exclusion or
external-upload exclusion — those are enforced on every path, override or not.

  * it needs BOTH ``--local-research-override`` and the exact acknowledgement
    sentence ``OVERRIDE_ACKNOWLEDGEMENT``;
  * it applies only to ``licence_pending`` datasets (quarantined, rejected or
    not-downloaded datasets stay refused);
  * it permits only the purposes in ``OVERRIDE_PURPOSES`` — local research
    conversion and a local exploratory analysis — and refuses every purpose in
    ``OVERRIDE_REFUSED_PURPOSES``;
  * it prints a visible warning that licensing and privacy approval are
    unresolved;
  * every use is appended to the private log
    ``<SAHAY_DATASETS_ROOT>/reports/overrides/override-log.jsonl``;
  * every record it produces carries ``governance_basis: local_research_override``;
  * it changes no registry field. It does not establish that any licence is
    valid, and it cannot supply data to the MVP, the product or the demo.

The blind corpus, the freeze gate and the locked corpus have no override
parameter at all; nothing in this module can reach them. No backend, frontend,
mobile or product module imports this adapter or reads its outputs, and a test
enforces that.

Streaming and determinism
-------------------------
Rows are read, normalised, de-duplicated and written one at a time, so a
230,000-row file is never held in memory; only duplicate keys are kept.
Records are emitted in source order, the first occurrence of a text wins, and
output is written to a partial file and moved into place (manifest last) only
when complete. A rerun over identical input reports ``unchanged``.

Quarantine and retention
------------------------
Every record and manifest is marked ``quarantined_research_artifact``. The
rule-based redactor removes URL, e-mail, handle, phone and long-number shapes
but cannot detect personal names, places or contextual identifiers, so the
output may still contain them. Retain it only while the analysis is actively
required and delete the normalised text once aggregate review is complete;
nothing here deletes it automatically.

No message, log line or exception carries record text: only dataset ids, row
numbers, counts and reason classes.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from ..eval.blind import leakage as lk
from ..eval.blind import normalize as nz
from ..eval.schema import IDENTIFYING_PATTERNS
from . import archive_safety as az
from . import governance as gov
from . import label_firewall as fw

ADAPTER_VERSION = "1.1.0"
RECORD_SCHEMA = "sahay-external-dev-record"
RECORD_SCHEMA_VERSION = "1.1.0"
REPO = Path(__file__).resolve().parents[2]

SPLITS = ("train", "validation", "test", "unsplit")
SPLIT_ALIASES = {"train": "train", "training": "train", "test": "test", "testing": "test",
                 "dev": "validation", "val": "validation", "valid": "validation", "validation": "validation"}
LANGUAGE_ALIASES = {"en": "en", "english": "en", "eng": "en", "hi": "hi", "hindi": "hi", "hin": "hi",
                    "hinglish": "hinglish", "hi-latn": "hinglish", "code-mixed": "hinglish",
                    "codemixed": "hinglish", "mixed": "hinglish"}
FORMATS = ("csv", "jsonl", "txt", "dialogue_csv")

# --- the override ------------------------------------------------------------------------------

OVERRIDE_FLAG = "--local-research-override"
OVERRIDE_ACKNOWLEDGEMENT = (
    "I authorise local offline exploratory research on a licence-pending dataset. Licensing and privacy approval "
    "remain unresolved. The data cannot enter the SAHAY product or demo and cannot be used for training, tuning, "
    "official evaluation or publication. I take responsibility for access to the private source files.")
#: Registry states the override may lift. Nothing else.
OVERRIDE_ELIGIBLE_STATES = ("licence_pending",)
#: The only purposes the override can serve.
OVERRIDE_PURPOSES = ("local_research_conversion", "local_research_exploratory_analysis")
#: Purposes nothing in this module can serve, override or not, whatever the acknowledgement says.
OVERRIDE_REFUSED_PURPOSES = ("mvp_product", "product", "demo", "victim_facing_output", "backend_ingestion",
                             "locked_test", "blind_corpus_intake", "corpus_freeze", "independent_evaluation",
                             "official_evaluation", "training", "threshold_tuning", "lexicon_tuning",
                             "model_tuning", "model_publication", "publication", "redistribution",
                             "commercial_use", "external_upload")
OVERRIDE_WARNING = ("WARNING: local exploratory research override in use. Licensing and privacy approval for this "
                    "dataset are UNRESOLVED. Output is a private, quarantined research artefact: it cannot enter the "
                    "product or demo, and must never be redistributed, published, uploaded, committed, or used for "
                    "training, tuning, the locked or blind corpus, or any independent or official evaluation.")
OVERRIDE_BASIS = "local_research_override"
ARTIFACT_CLASS = "quarantined_research_artifact"
RESIDUAL_IDENTIFIER_RISK = (
    "Private offline research artefact. Rule-based redaction cannot detect personal names, places or contextual "
    "identifiers, which may remain in this text. It cannot enter the product, demo, training, tuning, evaluation "
    "or publication.")
RETENTION_RECOMMENDATION = (
    "Retain only while this analysis is actively required; delete the normalised sensitive text once aggregate "
    "review is complete. Nothing deletes it automatically.")

NOT_INDEPENDENT = ("This record comes from an external dataset. It was not independently authored for SAHAY, "
                   "was not blind-annotated, and its labels were made for a different task.")
NOT_LOCKED = ("External data is never eligible for the locked corpus or the blind corpus, and a source test "
              "split is the publisher's split, not a SAHAY holdout.")
NO_MAPPING = ("No source label has been mapped to a SAHAY label, band, SVI dimension, routing decision or D4 "
              "value. Any mapping needs a separate human mapping record and a lead approval.")
D4_STATEMENT = "D4 is acoustic distress; a text record has no acoustic channel, so D4 is structurally unavailable."

#: Deterministic privacy redactions, applied in this order. Rule names only are reported.
REDACTIONS: Tuple[Tuple[str, "re.Pattern[str]", str], ...] = (
    ("url", re.compile(r"(https?://|www\.)\S+", re.IGNORECASE), "[URL]"),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    ("reddit_user", re.compile(r"(?<![\w/])/?u/[A-Za-z0-9_-]{3,}"), "[USER]"),
    ("reddit_community", re.compile(r"(?<![\w/])/?r/[A-Za-z0-9_]{2,}"), "[COMMUNITY]"),
    ("social_handle", re.compile(r"(?<![\w@])@[A-Za-z0-9_.]{2,}"), "[USER]"),
    ("phone", IDENTIFYING_PATTERNS["phone"], "[PHONE]"),
    ("long_number", IDENTIFYING_PATTERNS["long_number"], "[NUMBER]"),
)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")
NEAR_MIN_TOKENS = 6
_OVERLAP_RATIO = lk.OVERLAP_WARN


class AdapterRefused(Exception):
    """Conversion was refused by governance or configuration. Nothing was written."""


class MalformedSource(Exception):
    """The source file cannot be parsed at all. The message never quotes content."""


# --- dataset specifications ------------------------------------------------------------------

#: Adapter specs. ``ontology_verified`` records how the raw label values were
#: confirmed; conversion refuses an unverified ontology. The 2026-09-11 local
#: census counted label values only (never text) under the owner's local
#: exploratory research authorisation.
SPECS: Dict[str, Dict[str, Any]] = {
    "reddit_suicide_detection": {
        "format": "csv", "text_column": "text", "label_column": "class", "split_column": None,
        "language": "en", "language_column": None, "multi_label": False,
        "label_families": {"suicide": "suicide_related", "non-suicide": "non_suicide"},
        "ontology_verified": True,
        "ontology_evidence": "Kaggle metadata v14 and the local census: class in {suicide, non-suicide}, "
                             "116,037 each.",
    },
    "dreaddit": {
        "format": "csv", "text_column": "text", "label_column": "label", "split_column": None,
        "language": "en", "language_column": None, "multi_label": False,
        "label_families": {"1": "stress", "0": "other"},
        "local_copies": [{"relative_path": "archive(3)/dreaddit_StressAnalysis - Sheet1.csv", "byte_size": 685032,
                          "sha256": "568f0c7851a11521cda4eb955e2319de6f875982cbd426b645320d088400f70d",
                          "note": "third-party Kaggle re-upload; documented in the registry record"}],
        "ontology_verified": True,
        "ontology_evidence": "Paper: binary label, 1 = stress. Local census of the Kaggle copy: {1: 369, 0: 346}; "
                             "715 rows, the size of the paper's test split.",
    },
    "emoinhindi": {
        "format": "dialogue_csv", "text_column": "utterance", "label_column": "emotions",
        "dialogue_column": "dialogueId", "turn_column": "utterance_no", "speaker_column": "authorRole",
        "intensity_column": "emoIntensity", "split_column": None, "language": "hi", "language_column": None,
        "multi_label": True, "label_transform": "lower",
        "local_copies": [{"relative_path": "EmoInHindi/EmoInHindi/LREC_EmoInHindi.csv", "byte_size": 11730323,
                          "sha256": "05f4f7a1e829cb96a7db338602d86e414e5018df33c5a57c5924f4d7fe99d781",
                          "note": "already-extracted CSV; documented in the registry record"}],
        "label_families": {e: "emotion" for e in (
            "anticipation", "confident", "hopeful", "anger", "sad", "joy", "compassion", "fear", "disgusted",
            "annoyed", "grateful", "impressed", "apprehensive", "surprised", "guilty", "neutral", "confused")},
        "ontology_verified": True,
        "ontology_evidence": "Paper lists 16 classes; the local census found those 16 in lower case, comma-separated, "
                             "plus 'confused' (125 occurrences), which the paper does not list and is kept as an "
                             "observed source value.",
    },
    "hinglish_hate_speech_local_derivative": {
        "format": "csv", "text_column": "text", "label_column": "hate_label", "split_column": None,
        "language": None, "language_column": "language", "multi_label": False,
        "label_families": {"1.0": "hate_speech", "0.0": "not_hate_speech"},
        "ontology_verified": True,
        "ontology_evidence": "Local census: hate_label in {1.0: 7,500, 0.0: 7,500} on rows whose language is "
                             "'english'; 3,201 further rows have no label, language or source and are excluded. "
                             "1.0 read as hate from the column name; not confirmed by the publisher.",
    },
    "hinglish_sentiment_kaggle": {
        "format": "csv", "text_column": "text", "label_column": "sentiment_class", "split_column": None,
        "header_columns": ["source_row_index", "text", "sentiment_class"],
        "language": "hinglish", "language_column": None, "multi_label": False,
        "label_families": {"0": "sentiment_unspecified", "1": "sentiment_unspecified",
                           "2": "sentiment_unspecified"},
        "ontology_verified": True,
        "ontology_evidence": "Header-less file; the Kaggle metadata's 'field names' are its first data row, which "
                             "matches the local first row by hash. Local census: class in {0: 4,252, 1: 5,473, "
                             "2: 4,869}. What each class means is not published, so no polarity is assumed.",
    },
}


def validate_spec(spec: Mapping[str, Any]) -> List[str]:
    errs: List[str] = []
    if spec.get("format") not in FORMATS:
        errs.append(f"format must be one of {FORMATS}")
    if not spec.get("text_column"):
        errs.append("text_column is required")
    fams = spec.get("label_families")
    if not isinstance(fams, Mapping):
        errs.append("label_families must be an object")
    else:
        for raw, family in fams.items():
            if family not in fw.SOURCE_FAMILIES:
                errs.append(f"label {raw!r} has unknown family {family!r}")
            if fw.is_sahay_category(str(raw)):
                errs.append(f"raw label {raw!r} collides with a SAHAY category name")
    if spec.get("format") == "dialogue_csv":
        for key in ("dialogue_column", "turn_column"):
            if not spec.get(key):
                errs.append(f"{key} is required for dialogue_csv")
    if spec.get("language") is None and not spec.get("language_column"):
        errs.append("a spec needs a source-declared language or a language column")
    if spec.get("header_columns") is not None and not isinstance(spec.get("header_columns"), list):
        errs.append("header_columns must be a list")
    return errs


# --- governance and the override ---------------------------------------------------------------


def make_override(acknowledgement: str, operator: str = "unspecified") -> Dict[str, str]:
    """An override token. Valid only with the exact acknowledgement sentence."""
    return {"acknowledgement": acknowledgement, "operator": str(operator or "unspecified")[:80]}


def authorise(reg: Mapping[str, Any], dataset_id: str, purpose: str,
              override: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The governance basis for one use, or AdapterRefused. Fail-closed by default."""
    rec = gov.get(reg, dataset_id)
    if purpose in OVERRIDE_REFUSED_PURPOSES:
        raise AdapterRefused(f"{purpose} is never permitted for external data by this adapter")
    if override is None:
        try:
            gov.select_for(reg, dataset_id, "research")
        except gov.GovernanceError as exc:
            raise AdapterRefused(f"governance refused {dataset_id}: {exc}") from None
        return {"basis": "registry_approval", "review_status": rec["review_status"], "purpose": purpose}
    if purpose not in OVERRIDE_PURPOSES:
        raise AdapterRefused(f"the local exploratory research override does not cover {purpose!r}")
    if not isinstance(override, Mapping) or override.get("acknowledgement") != OVERRIDE_ACKNOWLEDGEMENT:
        raise AdapterRefused("the local exploratory research override needs the exact acknowledgement sentence")
    if rec["review_status"] not in OVERRIDE_ELIGIBLE_STATES:
        raise AdapterRefused(f"the local exploratory research override cannot lift {rec['review_status']}; only "
                             f"{OVERRIDE_ELIGIBLE_STATES} may be processed locally")
    if rec["download_status"] != "downloaded":
        raise AdapterRefused(f"{dataset_id} is not downloaded")
    return {"basis": OVERRIDE_BASIS, "review_status": rec["review_status"], "purpose": purpose,
            "licence_approved": False, "privacy_approved": False,
            "operator": override.get("operator", "unspecified"), "warning": OVERRIDE_WARNING}


def inside_sahay_worktree(path: Path) -> bool:
    """True if ``path`` is inside this repository or any other SAHAY checkout.

    A SAHAY checkout is recognised by carrying this governance module at its
    root, so sibling worktrees are protected too. An unrelated Git repository
    that happens to enclose the path is not treated as one.
    """
    path = Path(path).resolve()
    if REPO == path or REPO in path.parents:
        return True
    for parent in [path, *path.parents]:
        if (parent / ".git").exists() and (parent / "ml" / "data" / "governance.py").is_file():
            return True
    return False


def private_dir(root: Path, rel: str) -> Path:
    """A directory beneath the dataset root, never inside a SAHAY checkout."""
    dest = gov.resolve_under(Path(root), rel)
    if inside_sahay_worktree(dest):
        raise AdapterRefused("refusing to write inside a SAHAY Git worktree")
    return dest


def reports_dir(root: Path, name: str) -> Path:
    return private_dir(root, f"reports/{name}")


def output_dir(root: Path, dataset_id: str, file_sha: str) -> Path:
    return private_dir(root, f"normalized/{dataset_id}/{file_sha[:12]}")


def record_override_use(root: Path, entry: Mapping[str, Any]) -> Path:
    """Append one override-use entry to the private log. Ids, hashes and counts only."""
    log = reports_dir(root, "overrides") / "override-log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(dict(entry), sort_keys=True, ensure_ascii=False) + "\n")
    return log


# --- small pure helpers ------------------------------------------------------------------------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def script_of(text: str) -> str:
    dev, lat = len(_DEVANAGARI.findall(text)), len(_LATIN.findall(text))
    if dev and lat:
        return "mixed"
    if dev:
        return "devanagari"
    if lat:
        return "latin"
    return "none"


def redact(text: str) -> Tuple[str, Dict[str, int]]:
    """Apply every privacy redaction. Returns the text and per-rule counts."""
    counts: Dict[str, int] = {}
    out = str(text)
    for name, pattern, token in REDACTIONS:
        out, n = pattern.subn(token, out)
        if n:
            counts[name] = counts.get(name, 0) + n
    return out, counts


def normalise_language(value: Any) -> str:
    return LANGUAGE_ALIASES.get(str(value or "").strip().casefold(), "unknown")


def normalise_split(value: Any) -> Optional[str]:
    if value is None or str(value).strip() == "":
        return None
    return SPLIT_ALIASES.get(str(value).strip().casefold())


def exact_key(text: str) -> str:
    return sha256_text(nz.compare(text))


def near_key(text: str) -> Optional[str]:
    tokens = sorted(set(nz.token_list(text)))
    if len(tokens) < NEAR_MIN_TOKENS:
        return None
    return sha256_text(" ".join(tokens))


def record_id(dataset_id: str, split: str, row_sha: str) -> str:
    return f"EXT:{dataset_id}:{split}:{row_sha[:16]}"


# --- source readers ----------------------------------------------------------------------------
# Each yields (row_number, fields) or (row_number, {"__malformed__": reason}). Row
# numbers are 1-based data rows. Nothing here raises with content.


def _set_field_limit() -> None:
    limit = 2 ** 31 - 1
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 2


def read_csv(path: Path, header_columns: Optional[Sequence[str]] = None) -> Iterator[Tuple[int, Dict[str, Any]]]:
    _set_field_limit()
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        if header_columns is not None:
            header = list(header_columns)
        else:
            try:
                header = next(reader)
            except StopIteration:
                raise MalformedSource("the CSV is empty") from None
            except csv.Error:
                raise MalformedSource("the CSV header cannot be parsed") from None
        if len(set(header)) != len(header):
            header = [h if header.index(h) == i else f"{h}__{i}" for i, h in enumerate(header)]
        n = 0
        while True:
            try:
                row = next(reader)
            except StopIteration:
                if n == 0 and header_columns is not None:
                    raise MalformedSource("the CSV is empty") from None
                return
            except csv.Error:
                n += 1
                yield n, {"__malformed__": "csv_parse_error"}
                continue
            n += 1
            if not row or all(not c.strip() for c in row):
                yield n, {"__malformed__": "blank_row"}
                continue
            if len(row) != len(header):
                yield n, {"__malformed__": "column_count_mismatch"}
                continue
            if any("�" in v for v in row):
                yield n, {"__malformed__": "encoding_error"}
                continue
            yield n, dict(zip(header, row))


def read_jsonl(path: Path) -> Iterator[Tuple[int, Dict[str, Any]]]:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                yield n, {"__malformed__": "blank_row"}
                continue
            if "�" in line:
                yield n, {"__malformed__": "encoding_error"}
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                yield n, {"__malformed__": "invalid_json"}
                continue
            if not isinstance(obj, dict):
                yield n, {"__malformed__": "json_not_an_object"}
                continue
            yield n, obj


def read_txt(path: Path, text_column: str) -> Iterator[Tuple[int, Dict[str, Any]]]:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            line = line.rstrip("\r\n")
            if not line.strip():
                yield n, {"__malformed__": "blank_row"}
            elif "�" in line:
                yield n, {"__malformed__": "encoding_error"}
            else:
                yield n, {text_column: line}


def read_rows(path: Path, spec: Mapping[str, Any]) -> Iterator[Tuple[int, Dict[str, Any]]]:
    fmt = spec["format"]
    if fmt in ("csv", "dialogue_csv"):
        return read_csv(path, spec.get("header_columns"))
    if fmt == "jsonl":
        return read_jsonl(path)
    return read_txt(path, spec["text_column"])


# --- conversion --------------------------------------------------------------------------------


def _labels(raw: Any, spec: Mapping[str, Any]) -> Optional[List[str]]:
    """Raw label values for one row, or None when a value is outside the ontology."""
    text = str(raw).strip()
    if spec.get("multi_label"):
        values = [v.strip() for v in re.split(r"[,;|]", text)]
    else:
        values = [text]
    if spec.get("label_transform") == "lower":
        values = [v.lower() for v in values]
    values = [v for v in values if v]
    if spec.get("multi_label"):
        values = list(dict.fromkeys(values))  # drop repeats such as "confident,confident", keep order
    if not values or any(v not in spec["label_families"] for v in values):
        return None
    return values


def _has_label(raw: Any) -> bool:
    return raw is not None and str(raw).strip() != ""


def _base(dataset_id: str, rec: Mapping[str, Any], split: str, row_sha: str, language: str,
          language_basis: str, raw_label: Any, values: List[str], spec: Mapping[str, Any],
          basis: Mapping[str, Any]) -> Dict[str, Any]:
    families = sorted({spec["label_families"][v] for v in values})
    return {
        "schema": RECORD_SCHEMA,
        "schema_version": RECORD_SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "record_id": record_id(dataset_id, split, row_sha),
        "dataset_id": dataset_id,
        "dataset_version": rec["version"],
        "source_split": split,
        "split_note": "the publisher's split; not a SAHAY holdout" if split != "unsplit"
        else "the source publishes no split",
        "source_row_sha256": row_sha,
        "language": language,
        "language_basis": language_basis,
        "raw_source_label": raw_label,
        "source_label_category": [fw.source_category(dataset_id, v) for v in values],
        "source_label_family": families,
        "governance_basis": basis["basis"],
        "permitted_evaluation_purposes": (list(OVERRIDE_PURPOSES) if basis["basis"] == OVERRIDE_BASIS
                                          else sorted(set(rec["approved_uses"]) & {"research", "evaluation"})),
        "research_artifact": {"class": ARTIFACT_CLASS, "statement": RESIDUAL_IDENTIFIER_RISK},
        "independently_authored": False,
        "independently_authored_statement": NOT_INDEPENDENT,
        "locked_corpus_eligible": False,
        "locked_corpus_statement": NOT_LOCKED,
        "sahay_mapping": {"applied": False, "statement": NO_MAPPING},
        "d4": {"available": False, "statement": D4_STATEMENT},
    }


class ContaminationProbe:
    """Overlap checks against every exposed SAHAY corpus, fast enough to stream.

    Wraps ``leakage.check`` unchanged. The only speed-up is exact arithmetic: a
    Jaccard overlap of at least ``OVERLAP_WARN`` is impossible between two token
    sets whose sizes differ by more than that ratio, so exposed samples outside
    the size band are not offered to the overlap loop. Every other check sees
    the full index.
    """

    def __init__(self, index: Optional[Mapping[str, Any]] = None):
        self.index = dict(index if index is not None else lk.build_index())
        self.sizes = {sid: len(toks) for sid, toks in self.index["tokens"].items()}

    def check(self, texts: Sequence[str]) -> Dict[str, Any]:
        probe = {"turns": [{"id": f"t{i + 1}", "speaker": "victim", "text": t} for i, t in enumerate(texts)],
                 "lineage": None}
        n = len(nz.token_set(" ".join(texts)))
        view = dict(self.index)
        view["tokens"] = {sid: toks for sid, toks in self.index["tokens"].items()
                          if n and _OVERLAP_RATIO * self.sizes[sid] <= n <= self.sizes[sid] / _OVERLAP_RATIO}
        findings = lk.check(probe, view)
        worst = lk.worst(findings)
        return {"status": {"block": "exposed_overlap", "warn": "similarity_review_required",
                           None: "no_overlap_found"}[worst],
                "findings": [{"check": f["check"], "severity": f["severity"], "matched_id": f["matched_id"]}
                             for f in findings],
                "locked_corpus_eligible": False}


def contamination_status(record: Mapping[str, Any], index: Mapping[str, Any]) -> Dict[str, Any]:
    """Overlap of one record with every exposed SAHAY corpus. Ids, never text."""
    turns = record.get("turns") or [{"text": record.get("text", "")}]
    return ContaminationProbe(index).check([t["text"] for t in turns])


def iter_records(dataset_id: str, rec: Mapping[str, Any], spec: Mapping[str, Any], file_sha: str,
                 rows: Iterable[Tuple[int, Dict[str, Any]]], excluded: Counter,
                 probe: Optional[ContaminationProbe] = None,
                 basis: Optional[Mapping[str, Any]] = None) -> Iterator[Dict[str, Any]]:
    """Stream normalised records in source order. Exclusions are counted in ``excluded``.

    Duplicates are marked as records pass: the first occurrence of a text wins,
    and every record registers its own exact key, so an exact copy of a near
    duplicate is still recognised as exact.
    """
    probe = probe or ContaminationProbe()
    basis = basis or {"basis": "registry_approval"}
    seen_exact: Dict[str, str] = {}
    seen_near: Dict[str, str] = {}

    def finish(record: Dict[str, Any], texts: Sequence[str]) -> Dict[str, Any]:
        record["duplicate_of"], record["duplicate_kind"] = None, None
        if record["exact_key"] in seen_exact:
            record["duplicate_of"], record["duplicate_kind"] = seen_exact[record["exact_key"]], "exact"
        else:
            seen_exact[record["exact_key"]] = record["record_id"]
            if record["near_key"] and record["near_key"] in seen_near:
                record["duplicate_of"], record["duplicate_kind"] = seen_near[record["near_key"]], "near"
            elif record["near_key"]:
                seen_near[record["near_key"]] = record["record_id"]
        record["contamination"] = probe.check(list(texts))
        return record

    def language_for(fields: Mapping[str, Any]) -> Tuple[str, str]:
        if spec.get("language_column"):
            return normalise_language(fields.get(spec["language_column"])), "row_column"
        return (spec["language"] if spec.get("language") in ("en", "hi", "hinglish") else "unknown"), \
            "source_declared"

    def split_for(fields: Mapping[str, Any]) -> Optional[str]:
        col = spec.get("split_column")
        return "unsplit" if not col else normalise_split(fields.get(col))

    if spec["format"] != "dialogue_csv":
        for n, fields in rows:
            if "__malformed__" in fields:
                excluded[fields["__malformed__"]] += 1
                continue
            raw = fields.get(spec["label_column"]) if spec.get("label_column") else None
            if spec.get("label_column") and not _has_label(raw):
                excluded["missing_source_label"] += 1
                continue
            text = fields.get(spec["text_column"])
            if text is None or (isinstance(text, str) and not text.strip()):
                excluded["empty_text"] += 1
                continue
            if not isinstance(text, str):
                excluded["text_not_a_string"] += 1
                continue
            values = _labels(raw, spec) if spec.get("label_column") else []
            if values is None:
                excluded["unsupported_source_label"] += 1
                continue
            split = split_for(fields)
            if split is None:
                excluded["unsupported_split"] += 1
                continue
            language, lbasis = language_for(fields)
            row_sha = sha256_text(canonical({"file": file_sha, "row": n, "fields": fields}))
            clean, counts = redact(text.strip())
            record = _base(dataset_id, rec, split, row_sha, language, lbasis, raw, values, spec, basis)
            record.update({"text": clean, "script": script_of(clean),
                           "privacy_findings": [{"rule": r, "count": c} for r, c in sorted(counts.items())],
                           "exact_key": exact_key(clean), "near_key": near_key(clean),
                           "derivation": [{"step": "source_row", "detail": f"row {n}"},
                                          {"step": "whitespace_trim", "detail": "leading and trailing"},
                                          {"step": "privacy_redaction", "detail": sorted(counts)},
                                          {"step": "label_namespacing", "detail": "source:<dataset>:<value>"}]})
            yield finish(record, [clean])
        return

    dialogues: Dict[str, List[Tuple[int, int, Dict[str, Any]]]] = {}
    for n, fields in rows:
        if "__malformed__" in fields:
            excluded[fields["__malformed__"]] += 1
            continue
        did = str(fields.get(spec["dialogue_column"], "")).strip()
        try:
            turn_no = int(str(fields.get(spec["turn_column"], "")).strip())
        except ValueError:
            excluded["invalid_turn_number"] += 1
            continue
        if not did:
            excluded["missing_dialogue_id"] += 1
            continue
        dialogues.setdefault(did, []).append((turn_no, n, fields))
    for did, items in dialogues.items():  # first-appearance order
        items = sorted(items, key=lambda x: (x[0], x[1]))
        if len({t for t, _, _ in items}) != len(items):
            excluded["duplicate_turn_number"] += 1
            continue
        turns, all_values, findings, reason = [], [], [], None
        for position, (turn_no, n, fields) in enumerate(items):
            text = str(fields.get(spec["text_column"], "")).strip()
            raw = fields.get(spec["label_column"]) if spec.get("label_column") else None
            if not text:
                reason = "empty_text"
                break
            if spec.get("label_column") and not _has_label(raw):
                reason = "missing_source_label"
                break
            values = _labels(raw, spec) if spec.get("label_column") else []
            if values is None:
                reason = "unsupported_source_label"
                break
            clean, counts = redact(text)
            findings += [{"rule": r, "count": c, "turn": position} for r, c in sorted(counts.items())]
            turn = {"turn_index": position, "source_turn_number": turn_no,
                    "speaker": str(fields.get(spec.get("speaker_column") or "", "")).strip() or "unknown",
                    "text": clean, "script": script_of(clean), "raw_source_label": raw,
                    "source_label_category": [fw.source_category(dataset_id, v) for v in values]}
            if spec.get("intensity_column"):
                turn["raw_source_intensity"] = str(fields.get(spec["intensity_column"], "")).strip()
            turns.append(turn)
            all_values += values
        if reason:
            excluded[reason] += 1
            continue
        first = items[0][2]
        split = split_for(first)
        if split is None:
            excluded["unsupported_split"] += 1
            continue
        language, lbasis = language_for(first)
        row_sha = sha256_text(canonical({"file": file_sha, "dialogue": did, "rows": [[n, f] for _, n, f in items]}))
        joined = " ".join(t["text"] for t in turns)
        labels = sorted(set(all_values))
        record = _base(dataset_id, rec, split, row_sha, language, lbasis, labels, labels, spec, basis)
        record.update({"turns": turns, "script": script_of(joined), "privacy_findings": findings,
                       "exact_key": exact_key(joined), "near_key": near_key(joined),
                       "derivation": [{"step": "source_dialogue", "detail": f"{len(items)} rows grouped"},
                                      {"step": "turn_order", "detail": "ascending source turn number"},
                                      {"step": "privacy_redaction", "detail": sorted({f["rule"] for f in findings})},
                                      {"step": "label_namespacing", "detail": "source:<dataset>:<value>"}]})
        yield finish(record, [t["text"] for t in turns])


def convert_rows(dataset_id: str, rec: Mapping[str, Any], spec: Mapping[str, Any], file_sha: str,
                 rows: Iterable[Tuple[int, Dict[str, Any]]],
                 index: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """In-memory convenience wrapper over ``iter_records`` (small inputs and tests)."""
    excluded: Counter = Counter()
    records = list(iter_records(dataset_id, rec, spec, file_sha, rows, excluded, ContaminationProbe(index)))
    return {"records": records, "excluded": dict(sorted(excluded.items()))}


def mark_duplicates(records: List[Dict[str, Any]]) -> None:
    """Mark exact and near duplicates in list order (first occurrence wins)."""
    seen_exact: Dict[str, str] = {}
    seen_near: Dict[str, str] = {}
    for record in records:
        record["duplicate_of"] = None
        record["duplicate_kind"] = None
        if record["exact_key"] in seen_exact:
            record["duplicate_of"], record["duplicate_kind"] = seen_exact[record["exact_key"]], "exact"
            continue
        seen_exact[record["exact_key"]] = record["record_id"]
        if record["near_key"] and record["near_key"] in seen_near:
            record["duplicate_of"], record["duplicate_kind"] = seen_near[record["near_key"]], "near"
        elif record["near_key"]:
            seen_near[record["near_key"]] = record["record_id"]


def cross_dataset_overlap(datasets: Mapping[str, Iterable[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    """Exact and near copies that appear in more than one dataset. Ids and counts only."""
    by_key: Dict[Tuple[str, str], Dict[str, List[str]]] = {}
    for dataset_id, records in datasets.items():
        for r in records:
            for kind in ("exact", "near"):
                key = r.get(f"{kind}_key")
                if key:
                    by_key.setdefault((kind, key), {}).setdefault(dataset_id, []).append(r["record_id"])
    out = []
    for (kind, _), owners in sorted(by_key.items()):
        if len(owners) > 1:
            out.append({"kind": kind, "datasets": sorted(owners),
                        "record_ids": sorted(i for ids in owners.values() for i in ids)})
    return out


# --- governed conversion ------------------------------------------------------------------------


def resolve_source(root: Path, rec: Mapping[str, Any], spec: Mapping[str, Any]) -> Tuple[Path, str, str]:
    """The exact file to read: the registered file, or a pinned, documented local copy.

    A local copy is accepted only if its size and SHA-256 match the pin in the
    spec AND that SHA-256 is written in the reviewed registry record, so no
    unregistered bytes can be processed. Returns (path, sha256, kind).
    """
    if rec.get("local_relative_path"):
        registered = gov.resolve_under(root, rec["local_relative_path"])
        if registered.is_file():
            digest = az.sha256_file(registered)
            if digest != rec["sha256"] or registered.stat().st_size != rec["byte_size"]:
                raise AdapterRefused(f"{rec['id']}: integrity mismatch; refusing to convert")
            return registered, digest, "registered_file"
    record_text = json.dumps(rec, ensure_ascii=False)
    for copy in spec.get("local_copies") or []:
        path = gov.resolve_under(root, copy["relative_path"])
        if not path.is_file():
            continue
        if copy["sha256"] not in record_text:
            raise AdapterRefused(f"{rec['id']}: a pinned local copy is not documented in the registry record")
        digest = az.sha256_file(path)
        if digest != copy["sha256"] or path.stat().st_size != copy["byte_size"]:
            raise AdapterRefused(f"{rec['id']}: local copy integrity mismatch; refusing to convert")
        return path, digest, "documented_local_copy"
    raise AdapterRefused(f"{rec['id']}: the registered file is missing and no documented local copy is present")


def _documented(rec: Mapping[str, Any], digest: str) -> bool:
    """A source hash the reviewed registry record names: its own file or a documented copy."""
    return bool(digest) and (digest == rec.get("sha256") or digest in json.dumps(rec, ensure_ascii=False))


def convert(root: Path, dataset_id: str, registry: Optional[Mapping[str, Any]] = None,
            spec: Optional[Mapping[str, Any]] = None, index: Optional[Mapping[str, Any]] = None,
            override: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Governed, streaming conversion of one registered dataset.

    Refuses before reading any row unless governance permits it — through a
    registry approval, or through the explicit, acknowledged local exploratory research override.
    """
    reg = registry if registry is not None else gov.load_registry()
    if gov.validate_registry(reg):
        raise AdapterRefused("the registry is invalid; nothing was converted")
    rec = gov.get(reg, dataset_id)
    basis = authorise(reg, dataset_id, "local_research_conversion" if override else "research", override)
    if rec["download_status"] != "downloaded":
        raise AdapterRefused(f"{dataset_id} is not downloaded")
    spec = spec if spec is not None else SPECS.get(dataset_id)
    if spec is None:
        raise AdapterRefused(f"{dataset_id} has no adapter spec")
    errs = validate_spec(spec)
    if errs:
        raise AdapterRefused(f"{dataset_id}: adapter spec invalid: " + "; ".join(errs))
    if not spec.get("ontology_verified"):
        raise AdapterRefused(f"{dataset_id}: the source label ontology is not verified; a human must confirm it")
    src, digest, source_kind = resolve_source(Path(root), rec, spec)
    dest = output_dir(Path(root), dataset_id, digest)
    dest.mkdir(parents=True, exist_ok=True)
    records_path, manifest_path = dest / "records.jsonl", dest / "manifest.json"
    partial = dest / "records.jsonl.partial"
    started = now()

    excluded: Counter = Counter()
    stats: Counter = Counter()
    hasher = hashlib.sha256()

    def counted(rows: Iterable[Tuple[int, Dict[str, Any]]]) -> Iterator[Tuple[int, Dict[str, Any]]]:
        for item in rows:
            stats["source_rows"] += 1
            yield item

    try:
        with open(partial, "w", encoding="utf-8", newline="\n") as out:
            for record in iter_records(dataset_id, rec, spec, digest, counted(read_rows(src, spec)), excluded,
                                       ContaminationProbe(index), basis):
                line = canonical(record) + "\n"
                hasher.update(line.encode("utf-8"))
                out.write(line)
                stats["records"] += 1
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    records_sha = hasher.hexdigest()
    manifest = {
        "schema": RECORD_SCHEMA, "adapter_version": ADAPTER_VERSION, "dataset_id": dataset_id,
        "dataset_version": rec["version"], "source_sha256": digest, "records": stats["records"],
        "source_rows_read": stats["source_rows"],
        "units_discovered": stats["records"] + sum(excluded.values()),
        "unit": "dialogue" if spec["format"] == "dialogue_csv" else "row",
        "excluded": dict(sorted(excluded.items())), "records_sha256": records_sha,
        "spec_sha256": sha256_text(canonical(spec)), "governance_basis": basis["basis"],
        "source_file": source_kind,
        "processing": "full dataset, streamed",
        "artifact_class": ARTIFACT_CLASS,
        "residual_identifier_risk": RESIDUAL_IDENTIFIER_RISK,
        "retention_recommendation": RETENTION_RECOMMENDATION,
        "note": "Private research output. Never commit, print, upload, redistribute, show to a victim, or feed to "
                "the product, demo, training, tuning or any evaluation claim.",
    }
    if basis["basis"] == OVERRIDE_BASIS:
        manifest["override"] = {k: basis[k] for k in ("purpose", "operator", "licence_approved", "privacy_approved",
                                                      "warning")}

    unchanged = False
    if manifest_path.is_file() and records_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            existing = {}
        unchanged = existing == json.loads(json.dumps(manifest)) and az.sha256_file(records_path) == records_sha
    if unchanged:
        partial.unlink(missing_ok=True)
    else:
        os.replace(partial, records_path)
        tmp = manifest_path.with_name("manifest.json.partial")
        tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, manifest_path)  # the manifest is written last: it marks a complete output
    if basis["basis"] == OVERRIDE_BASIS:
        record_override_use(root, {"event": "local_research_override_conversion", "at": started,
                                   "dataset_id": dataset_id, "source_sha256": digest, "records": stats["records"],
                                   "records_sha256": records_sha, "operator": basis["operator"],
                                   "licence_approved": False, "privacy_approved": False,
                                   "status": "unchanged" if unchanged else "written"})
    return {"dataset_id": dataset_id, "status": "unchanged" if unchanged else "written", "records": stats["records"],
            "source_rows_read": manifest["source_rows_read"], "units_discovered": manifest["units_discovered"],
            "unit": manifest["unit"], "excluded": manifest["excluded"],
            "records_sha256": records_sha, "governance_basis": basis["basis"]}


def iter_normalized(root: Path, dataset_id: str, registry: Optional[Mapping[str, Any]] = None
                    ) -> Optional[Iterator[Dict[str, Any]]]:
    """Stream previously converted records for a dataset, or None if there are none."""
    path = _normalized_dir(root, dataset_id, registry)
    if path is None:
        return None
    path = path / "records.jsonl"

    def gen() -> Iterator[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)
    return gen()


def load_normalized(root: Path, dataset_id: str, registry: Optional[Mapping[str, Any]] = None
                    ) -> Optional[List[Dict[str, Any]]]:
    it = iter_normalized(root, dataset_id, registry)
    return None if it is None else list(it)


def load_manifest(root: Path, dataset_id: str, registry: Optional[Mapping[str, Any]] = None
                  ) -> Optional[Dict[str, Any]]:
    path = _normalized_dir(root, dataset_id, registry)
    return None if path is None else json.loads((path / "manifest.json").read_text(encoding="utf-8"))


def _normalized_dir(root: Path, dataset_id: str, registry: Optional[Mapping[str, Any]] = None) -> Optional[Path]:
    """The completed output directory for a dataset (manifest present), or None."""
    reg = registry if registry is not None else gov.load_registry()
    rec = gov.get(reg, dataset_id)
    base = gov.resolve_under(Path(root), f"normalized/{dataset_id}")
    if not base.is_dir():
        return None
    for path in sorted(p for p in base.iterdir() if p.is_dir()):
        manifest = path / "manifest.json"
        if not manifest.is_file() or not (path / "records.jsonl").is_file():
            continue
        try:
            source = json.loads(manifest.read_text(encoding="utf-8")).get("source_sha256", "")
        except ValueError:
            continue
        if _documented(rec, source) and path.name == source[:12]:
            return path
    return None


# --- command line -------------------------------------------------------------------------------


def add_override_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(OVERRIDE_FLAG, dest="local_research_override", action="store_true",
                        help="owner-authorised private offline exploratory research on a licence_pending dataset; "
                             "bypasses only the licence-based read gate")
    parser.add_argument("--acknowledge", default="", help="the exact OVERRIDE_ACKNOWLEDGEMENT sentence")
    parser.add_argument("--operator", default="unspecified", help="who authorised this run (recorded privately)")


def override_from_args(args: argparse.Namespace) -> Optional[Dict[str, str]]:
    if not getattr(args, "local_research_override", False):
        return None
    if args.acknowledge != OVERRIDE_ACKNOWLEDGEMENT:
        raise AdapterRefused(f"{OVERRIDE_FLAG} needs --acknowledge with the exact sentence: "
                             f"{OVERRIDE_ACKNOWLEDGEMENT!r}")
    print(OVERRIDE_WARNING)
    return make_override(args.acknowledge, args.operator)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SAHAY-AI external-corpus adapter (private exploratory research)")
    parser.add_argument("--root", default=None, help=f"dataset root (default: ${gov.ROOT_ENV})")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("specs", help="list adapter specs and whether each ontology is verified")
    c = sub.add_parser("convert", help="convert one dataset if governance, or an acknowledged override, permits")
    c.add_argument("--dataset", required=True)
    add_override_arguments(c)
    args = parser.parse_args(argv)

    if args.cmd == "specs":
        for dataset_id, spec in sorted(SPECS.items()):
            print(f"{dataset_id}: format {spec['format']}, ontology verified {spec['ontology_verified']}, "
                  f"{len(spec['label_families'])} source label(s)")
        return 0
    try:
        override = override_from_args(args)
        root = gov.dataset_root(args.root)
        result = convert(root, args.dataset, override=override)
    except (gov.DatasetRootError, gov.GovernanceError) as exc:
        print(f"configuration: {exc}")
        return 4
    except AdapterRefused as exc:
        print(f"conversion refused: {exc}")
        return 3
    except MalformedSource as exc:
        print(f"conversion failed: {exc}")
        return 2
    print(f"{result['dataset_id']}: {result['status']} ({result['governance_basis']}), "
          f"{result['source_rows_read']} source row(s) read, {result['units_discovered']} {result['unit']}(s), "
          f"{result['records']} record(s), "
          f"excluded {sum(result['excluded'].values())} ({', '.join(sorted(result['excluded'])) or 'none'}), "
          f"records sha256 {result['records_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
