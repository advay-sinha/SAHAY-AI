"""Model root, path confinement, the portable manifest and file integrity. Standard library only.

The model root comes from ``SAHAY_MODELS_ROOT`` or an explicit argument. There is no default
path: a missing root is an explicit "unavailable" state, never a guess. Every path this
package touches is resolved and confined beneath that root, and the root may not sit inside
a SAHAY checkout, so weights can never land in Git.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

ROOT_ENV = "SAHAY_MODELS_ROOT"
REPORTS_ENV = "SAHAY_MODEL_REPORTS_ROOT"
ROOT_LABEL = "<SAHAY_MODELS_ROOT>"
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
MANIFEST_SCHEMA_VERSION = "1.0.0"

KINDS = ("text_encoder", "asr", "vad")
ROLES = ("primary_text_encoder", "comparison_text_encoder", "speech_to_text", "voice_activity_detection")
LICENCES = ("apache-2.0", "mit")
APPROVAL_STATES = ("approved_for_local_runtime_benchmark",)
REQUIRED_FIELDS = (
    "logical_id", "role", "kind", "upstream_repo", "source", "revision", "purpose", "licence", "architecture",
    "parameter_count", "claimed_languages", "expected_input", "local_env", "gated", "token_required",
    "fine_tuned_for_sahay", "approval_status", "files", "integrity",
)
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_MACHINE_PATH = re.compile(r"[A-Za-z]:[\\/]|\\\\|/Users/|/home/|AppData", re.I)


class RuntimeConfigError(Exception):
    """A configuration problem. Messages never contain an absolute path or any input."""


# --- root and confinement ---------------------------------------------------------------------


def _inside_sahay_checkout(path: Path) -> bool:
    for parent in (path, *path.parents):
        if (parent / ".git").exists() and (parent / "ml" / "runtime" / "manifest.json").is_file():
            return True
    return False


def models_root(explicit: Optional[str] = None) -> Path:
    """The resolved model root. Raises ``RuntimeConfigError`` when it is unset, missing or unsafe."""
    raw = explicit if explicit else os.environ.get(ROOT_ENV, "")
    if not raw.strip():
        raise RuntimeConfigError(f"{ROOT_ENV} is not set and no --models-root was given; the model root has no default")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise RuntimeConfigError(f"the model root given by {ROOT_ENV} does not exist or is not a directory")
    if _inside_sahay_checkout(root):
        raise RuntimeConfigError("the model root is inside a SAHAY checkout; weights must stay outside Git")
    return root


def reports_dir(explicit: Optional[str] = None) -> Optional[Path]:
    """Where private runtime reports go, or ``None`` (print aggregates only, write nothing)."""
    raw = explicit if explicit else os.environ.get(REPORTS_ENV, "")
    if not raw.strip():
        return None
    path = Path(raw).expanduser().resolve()
    if _inside_sahay_checkout(path):
        raise RuntimeConfigError("the reports directory is inside a SAHAY checkout; private reports stay outside Git")
    path.mkdir(parents=True, exist_ok=True)
    return path


def confined(root: Path, *parts: str) -> Path:
    """``root / parts`` resolved, refusing anything that escapes the root."""
    for part in parts:
        if not part or Path(part).is_absolute() or part.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", part):
            raise RuntimeConfigError("absolute or empty path component refused")
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise RuntimeConfigError("path escapes the model root") from None
    return target


def label(path: Path, root: Path) -> str:
    """A printable, machine-independent form of a path beneath the root."""
    try:
        return ROOT_LABEL + "/" + path.resolve().relative_to(root).as_posix()
    except ValueError:
        return "<outside-model-root>"


# --- manifest ---------------------------------------------------------------------------------


def load_manifest(path: Path = MANIFEST_PATH) -> Dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_manifest(manifest)
    if errors:
        raise RuntimeConfigError("invalid model manifest: " + "; ".join(errors))
    return manifest


def validate_manifest(manifest: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("unknown manifest schema_version")
    if manifest.get("root_env") != ROOT_ENV:
        errors.append(f"root_env must be {ROOT_ENV}")
    if _MACHINE_PATH.search(json.dumps(manifest)):
        errors.append("the manifest contains a machine-specific path")
    models = manifest.get("models")
    if not isinstance(models, list) or not models:
        return errors + ["models must be a non-empty list"]
    ids, roles = set(), []
    for entry in models:
        errors += [f"{entry.get('logical_id', '?')}: {e}" for e in validate_entry(entry)]
        if entry.get("logical_id") in ids:
            errors.append(f"duplicate logical_id {entry.get('logical_id')}")
        ids.add(entry.get("logical_id"))
        roles.append(entry.get("role"))
    for role in ROLES:
        if roles.count(role) != 1:
            errors.append(f"exactly one model must hold role {role}")
    return errors


def validate_entry(entry: Mapping[str, Any]) -> List[str]:
    errors = [f"missing field {f}" for f in REQUIRED_FIELDS if f not in entry]
    if errors:
        return errors
    if not _ID.match(str(entry["logical_id"])):
        errors.append("logical_id must be snake_case")
    if entry["kind"] not in KINDS:
        errors.append("unknown kind")
    if entry["role"] not in ROLES:
        errors.append("unknown role")
    if not _HEX40.match(str(entry["revision"])):
        errors.append("revision must be an immutable 40-hex commit, not a branch or tag")
    if entry["licence"] not in LICENCES:
        errors.append("licence is not on the approved list")
    if entry["approval_status"] not in APPROVAL_STATES:
        errors.append("model is not approved")
    if entry["gated"] is not False or entry["token_required"] is not False:
        errors.append("gated or token-requiring models are excluded")
    if entry["fine_tuned_for_sahay"] is not False:
        errors.append("no SAHAY fine-tuned model is approved")
    if entry["local_env"] != ROOT_ENV:
        errors.append(f"local_env must be {ROOT_ENV}")
    if entry["source"] == "huggingface" and not entry["files"]:
        errors.append("a Hugging Face model must list its required files")
    for f in entry["files"]:
        errors += [f"file {f.get('path', '?')}: {e}" for e in _validate_file(f)]
    return errors


def _validate_file(f: Mapping[str, Any]) -> List[str]:
    errors = []
    path = str(f.get("path", ""))
    if not path or Path(path).is_absolute() or ".." in Path(path).parts or "\\" in path:
        errors.append("path must be a relative POSIX path inside the model directory")
    if not isinstance(f.get("bytes"), int) or f["bytes"] <= 0:
        errors.append("bytes must be a positive integer")
    has_sha, has_blob = "sha256" in f, "git_blob_sha1" in f
    if has_sha == has_blob:
        errors.append("exactly one of sha256 or git_blob_sha1 is required")
    elif has_sha and not _HEX64.match(str(f["sha256"])):
        errors.append("sha256 must be 64 hex characters")
    elif has_blob and not _HEX40.match(str(f["git_blob_sha1"])):
        errors.append("git_blob_sha1 must be 40 hex characters")
    return errors


def get_model(manifest: Mapping[str, Any], logical_id: str) -> Dict[str, Any]:
    for entry in manifest["models"]:
        if entry["logical_id"] == logical_id:
            return dict(entry)
    raise RuntimeConfigError(f"unknown model {logical_id!r}")


def model_dir(root: Path, entry: Mapping[str, Any]) -> Path:
    return confined(root, entry["logical_id"], entry["revision"])


def derived_dir(root: Path, entry: Mapping[str, Any]) -> Path:
    derived = entry.get("derived")
    if not derived:
        raise RuntimeConfigError(f"{entry['logical_id']} has no derived artefact")
    return confined(root, entry["logical_id"], f"{entry['revision']}-{derived['name']}")


# --- integrity --------------------------------------------------------------------------------


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def git_blob_sha1(path: Path, chunk: int = 1 << 20) -> str:
    """The Git blob id of a file: sha1(b"blob <size>\\0" + content), as Hugging Face publishes it."""
    h = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify_files(directory: Path, files: Iterable[Mapping[str, Any]], *, full_hash: bool = True) -> Dict[str, Any]:
    """Check presence, size and (optionally) the upstream hash of every required file."""
    result: Dict[str, Any] = {"checked": 0, "bytes": 0, "missing": [], "size_mismatch": [], "hash_mismatch": [],
                              "hash_verified": full_hash}
    for f in files:
        path = directory / f["path"]
        result["checked"] += 1
        if not path.is_file():
            result["missing"].append(f["path"])
            continue
        size = path.stat().st_size
        result["bytes"] += size
        if size != f["bytes"]:
            result["size_mismatch"].append(f["path"])
            continue
        if full_hash:
            actual = sha256_file(path) if "sha256" in f else git_blob_sha1(path)
            if actual != f.get("sha256", f.get("git_blob_sha1")):
                result["hash_mismatch"].append(f["path"])
    result["ok"] = not (result["missing"] or result["size_mismatch"] or result["hash_mismatch"])
    return result


def inventory(directory: Path, root: Path) -> List[Dict[str, Any]]:
    """Every file beneath ``directory`` with its size and SHA-256, paths relative to the root."""
    rows = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        rows.append({"path": label(path, root), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return rows
