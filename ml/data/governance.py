"""Dataset registry: schema validation, dataset-root confinement and use guards.

Standard library only. The registry (`ml/data/registry/datasets.json`) holds
METADATA ONLY: no raw data, no sample text, no machine-specific path. Local
files are located as `<SAHAY_DATASETS_ROOT>/<local_relative_path>`.

Guards enforced here (and tested in ml/tests/test_dataset_governance.py):
  * a dataset may be selected for a purpose only in an approved review state;
  * a downloaded file is never approved automatically;
  * Dreaddit (or any dataset with official_locked_test_allowed = false) can
    never serve as the official locked test set;
  * no external dataset may populate D4 without an approved mapping study.
"""

import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Optional

REGISTRY_DIR = Path(__file__).resolve().parent / "registry"
REGISTRY_PATH = REGISTRY_DIR / "datasets.json"
ROOT_ENV = "SAHAY_DATASETS_ROOT"
REGISTRY_SCHEMA_VERSION = "1.0.0"

REVIEW_STATES = (
    "unregistered", "metadata_pending", "licence_pending", "quarantined", "integrity_verified",
    "approved_for_research", "approved_for_evaluation", "approved_for_training", "rejected",
)
#: Which review states permit which purpose. Nothing else is approved.
PURPOSE_STATES = {
    "research": ("approved_for_research", "approved_for_evaluation", "approved_for_training"),
    "evaluation": ("approved_for_evaluation", "approved_for_training"),
    "training": ("approved_for_training",),
}
MODALITIES = ("text", "audio", "audio_text", "multimodal")
#: en = English; hi = Hindi in Devanagari; hi-Latn = romanised Hindi / Hinglish;
#: mul-IN = multilingual Indian (several Indian languages).
LANGUAGES = ("en", "hi", "hi-Latn", "mul-IN", "unknown")
DOWNLOAD_STATUSES = ("downloaded", "not_downloaded")
ARCHIVE_SAFETY = ("not_checked", "passed", "failed", "not_applicable")
EXTRACTION = ("not_extracted", "extracted", "prohibited", "not_applicable")
TRISTATE = ("permitted", "not_permitted", "unknown")
HOLDOUT = ("not_holdout", "external_validation_candidate", "external_test_candidate")

REQUIRED_FIELDS = (
    "id", "name", "version", "modality", "primary_language", "additional_languages", "sahay_purpose",
    "source_page", "download_source", "publisher", "citation", "licence_name", "licence_url",
    "redistribution", "commercial_use", "research_only_restrictions", "attribution_requirements",
    "consent_statement", "privacy_risks", "demographics", "label_definitions", "splits",
    "local_relative_path", "archive_filename", "byte_size", "sha256", "archive_safety_status",
    "extraction_status", "review_status", "approved_uses", "prohibited_uses", "contamination_risk",
    "limitations", "date_checked", "evidence_urls", "unresolved_questions",
    "download_status", "ext_decision", "holdout_status", "sahay_dimension_mappings",
    "official_locked_test_allowed",
)
#: Fields that must be resolved (not "unknown"/empty) before any approval.
LICENCE_FIELDS = ("licence_name", "licence_url", "redistribution", "commercial_use")
PRE_LICENCE_STATES = ("unregistered", "metadata_pending", "licence_pending", "quarantined", "rejected")

_ID = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MACHINE_PATH = re.compile(r"([A-Za-z]:[\\/])|(^/(home|Users|mnt|var|tmp)/)|(\\\\)")


class GovernanceError(Exception):
    """Raised when a use is not permitted by the registry."""


class DatasetRootError(Exception):
    """Raised for a missing or unsafe dataset root / path."""


def load_registry(path: Path = REGISTRY_PATH) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _is_blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {} or value == "unknown"


def validate_record(rec: Mapping[str, Any]) -> List[str]:
    """Structural problems in one record. Empty list = valid shape."""
    errs: List[str] = []
    rid = str(rec.get("id", "<no id>"))
    missing = [f for f in REQUIRED_FIELDS if f not in rec]
    extra = [f for f in rec if f not in REQUIRED_FIELDS]
    if missing:
        errs.append(f"{rid}: missing fields {missing}")
    if extra:
        errs.append(f"{rid}: unknown fields {extra}")
    if missing:
        return errs
    if not _ID.match(rid):
        errs.append(f"{rid}: invalid id")
    for field, allowed in (("modality", MODALITIES), ("primary_language", LANGUAGES),
                           ("review_status", REVIEW_STATES), ("download_status", DOWNLOAD_STATUSES),
                           ("archive_safety_status", ARCHIVE_SAFETY), ("extraction_status", EXTRACTION),
                           ("redistribution", TRISTATE), ("commercial_use", TRISTATE),
                           ("holdout_status", HOLDOUT)):
        if rec[field] not in allowed:
            errs.append(f"{rid}: {field}={rec[field]!r} not in {allowed}")
    for lang in rec["additional_languages"]:
        if lang not in LANGUAGES:
            errs.append(f"{rid}: additional language {lang!r}")
    if not _DATE.match(str(rec["date_checked"])):
        errs.append(f"{rid}: date_checked must be YYYY-MM-DD")
    for f in ("approved_uses", "prohibited_uses", "evidence_urls", "unresolved_questions", "limitations",
              "privacy_risks"):
        if not isinstance(rec[f], list):
            errs.append(f"{rid}: {f} must be a list")
    if not isinstance(rec["official_locked_test_allowed"], bool):
        errs.append(f"{rid}: official_locked_test_allowed must be a bool")
    if not isinstance(rec["sahay_dimension_mappings"], dict):
        errs.append(f"{rid}: sahay_dimension_mappings must be an object")

    if rec["download_status"] == "downloaded":
        if not _SHA.match(str(rec["sha256"] or "")):
            errs.append(f"{rid}: a downloaded dataset needs a sha256")
        if not isinstance(rec["byte_size"], int) or rec["byte_size"] <= 0:
            errs.append(f"{rid}: a downloaded dataset needs a byte_size")
        rel = rec["local_relative_path"]
        if not rel or not safe_relative(rel):
            errs.append(f"{rid}: local_relative_path must be a safe relative path")
    else:
        if rec["review_status"] not in ("unregistered", "metadata_pending", "licence_pending", "rejected"):
            errs.append(f"{rid}: a not-downloaded dataset cannot be {rec['review_status']}")

    # Unresolved licence terms keep a dataset at or before licence_pending (or quarantined/rejected).
    unresolved = [f for f in LICENCE_FIELDS if _is_blank(rec[f])]
    if unresolved and rec["review_status"] not in PRE_LICENCE_STATES:
        errs.append(f"{rid}: {rec['review_status']} with unresolved licence fields {unresolved}; "
                    "must stay licence_pending, quarantined or rejected")
    # Approval states also need a record of use limits.
    if rec["review_status"].startswith("approved_"):
        if rec["archive_safety_status"] == "failed":
            errs.append(f"{rid}: approved state with a failed archive-safety check")
        if not rec["approved_uses"]:
            errs.append(f"{rid}: approved state without approved_uses")
    if rec["holdout_status"] != "not_holdout" and not rec["review_status"].startswith("approved_for_evaluation") \
            and rec["review_status"] != "approved_for_training":
        errs.append(f"{rid}: holdout_status {rec['holdout_status']} needs an evaluation approval")
    for key, value in rec["sahay_dimension_mappings"].items():
        if not (isinstance(value, dict) and value.get("approved_study_id")):
            errs.append(f"{rid}: dimension mapping {key} lacks an approved study id")

    # No machine-specific absolute path may enter the committed registry.
    for field in ("local_relative_path", "archive_filename"):
        if _MACHINE_PATH.search(str(rec[field] or "")):
            errs.append(f"{rid}: {field} contains a machine-specific path")
    return errs


def validate_registry(reg: Mapping[str, Any]) -> List[str]:
    errs: List[str] = []
    if not isinstance(reg, Mapping):
        return ["registry must be a JSON object"]
    if reg.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        errs.append(f"registry schema_version must be {REGISTRY_SCHEMA_VERSION}")
    records = reg.get("datasets")
    if not isinstance(records, list) or not all(isinstance(r, Mapping) for r in records):
        return errs + ["registry needs a datasets list of objects"]
    ids = [r.get("id") for r in records]
    if len(ids) != len(set(ids)):
        errs.append("duplicate dataset ids")
    for r in records:
        try:
            errs.extend(validate_record(r))
        except (TypeError, AttributeError):  # wrong JSON types in a field
            errs.append(f"{r.get('id', '<no id>')}: malformed field types")
    blob = json.dumps(reg, ensure_ascii=False)
    if _MACHINE_PATH.search(blob.replace("https://", "").replace("http://", "")):
        errs.append("registry contains a machine-specific path")
    return errs


def get(reg: Mapping[str, Any], dataset_id: str) -> Dict[str, Any]:
    for r in reg["datasets"]:
        if r["id"] == dataset_id:
            return r
    raise GovernanceError(f"dataset {dataset_id!r} is not registered")


# --- use guards -----------------------------------------------------------------------


def select_for(reg: Mapping[str, Any], dataset_id: str, purpose: str) -> Dict[str, Any]:
    """Return the record only if its review state permits `purpose`."""
    if purpose not in PURPOSE_STATES:
        raise GovernanceError(f"unknown purpose {purpose!r}")
    rec = get(reg, dataset_id)
    if rec["review_status"] not in PURPOSE_STATES[purpose]:
        raise GovernanceError(f"{dataset_id} is {rec['review_status']}: not approved for {purpose}")
    if purpose in rec["prohibited_uses"]:
        raise GovernanceError(f"{dataset_id}: {purpose} is a prohibited use")
    return rec


def assert_can_be_locked_test(reg: Mapping[str, Any], dataset_id: str) -> None:
    """External data never becomes the official locked set by default."""
    rec = get(reg, dataset_id)
    if not rec["official_locked_test_allowed"]:
        raise GovernanceError(f"{dataset_id} may not serve as the official locked test set")
    select_for(reg, dataset_id, "evaluation")


def assert_can_populate_dimension(reg: Mapping[str, Any], dataset_id: str, dimension: str) -> None:
    """Labels alone never populate an SVI dimension (D4 in particular)."""
    rec = get(reg, dataset_id)
    mapping = rec["sahay_dimension_mappings"].get(dimension)
    if not mapping or not mapping.get("approved_study_id"):
        raise GovernanceError(f"{dataset_id} has no approved mapping study for {dimension}")
    select_for(reg, dataset_id, "evaluation")


def governance_gaps(rec: Mapping[str, Any]) -> List[str]:
    """Unresolved governance items (reported by the audit; never auto-fixed)."""
    gaps = [f"licence:{f}" for f in LICENCE_FIELDS if _is_blank(rec[f])]
    if not rec["review_status"].startswith("approved_"):
        gaps.append(f"review_status:{rec['review_status']}")
    if not str(rec["ext_decision"]).endswith("APPROVED"):
        gaps.append(f"ext_decision:{rec['ext_decision']}")
    gaps += [f"question:{i + 1}" for i, _ in enumerate(rec["unresolved_questions"])]
    return gaps


# --- dataset-root confinement --------------------------------------------------------


def safe_relative(rel: str) -> bool:
    p = PurePosixPath(str(rel).replace("\\", "/"))
    return bool(str(rel)) and not p.is_absolute() and ".." not in p.parts and ":" not in str(rel) \
        and not str(rel).startswith(("/", "\\"))


def dataset_root(explicit: Optional[str] = None) -> Path:
    """The configured root. A clear, non-sensitive error if it is missing."""
    value = explicit or os.environ.get(ROOT_ENV)
    if not value:
        raise DatasetRootError(f"{ROOT_ENV} is not set and no --root was given; external datasets are optional "
                               f"and no default path is assumed")
    root = Path(value)
    if not root.is_dir():
        raise DatasetRootError("the configured dataset root does not exist or is not a directory")
    return root.resolve()


def resolve_under(root: Path, rel: str) -> Path:
    """Resolve a registry-relative path and refuse anything outside `root`."""
    if not safe_relative(rel):
        raise DatasetRootError("unsafe relative path in registry")
    target = (Path(root) / rel).resolve()
    root = Path(root).resolve()
    if target != root and root not in target.parents:
        raise DatasetRootError("path escapes the dataset root")
    return target
