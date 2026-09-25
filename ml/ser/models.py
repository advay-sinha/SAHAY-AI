"""Pinned SER backbone download and verification. Never runs on import or in tests.

    python -m ml.ser.models plan
    python -m ml.ser.models fetch --model all          # or emotion2vec_plus_large / wavlm_base_plus
    python -m ml.ser.models verify

``fetch`` downloads anonymously (``token=False``) at the manifest's immutable revision, only the
files the manifest lists, into ``<SAHAY_MODELS_ROOT>/<logical_id>/<revision>/``. It checks free
disk space first and afterwards verifies every size and upstream hash. The owner runs it by hand
(run point R1). Output is aggregate only: no absolute path, no token.
"""

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..runtime import config
from ..runtime.download import DISK_MARGIN_BYTES, _hf_env, free_bytes

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"
SCHEMA_VERSION = "ser-1.0.0"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
REQUIRED = ("logical_id", "role", "upstream_repo", "source", "revision", "decision", "licence", "use",
            "environment", "native_labels", "contamination", "gated", "token_required", "files")
ROLES = ("ser_primary_candidate", "ser_alternate")


def validate(manifest: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("unknown SER manifest schema_version")
    if manifest.get("root_env") != config.ROOT_ENV:
        errors.append(f"root_env must be {config.ROOT_ENV}")
    blob = json.dumps(manifest)
    if re.search(r"[A-Za-z]:[\\/]|/home/|/Users/", blob):
        errors.append("the manifest contains a machine-specific path")
    models = manifest.get("models") or []
    if not models:
        return errors + ["models must be a non-empty list"]
    seen = set()
    for m in models:
        mid = m.get("logical_id", "?")
        errors += [f"{mid}: missing {f}" for f in REQUIRED if f not in m]
        if any(f not in m for f in REQUIRED):
            continue
        if not _ID.match(mid) or mid in seen:
            errors.append(f"{mid}: invalid or duplicate logical_id")
        seen.add(mid)
        if m["role"] not in ROLES:
            errors.append(f"{mid}: unknown role")
        if m["source"] != "huggingface" or not _HEX40.match(m["revision"]):
            errors.append(f"{mid}: must be a Hugging Face repo pinned to a 40-hex commit")
        if m["gated"] is not False or m["token_required"] is not False:
            errors.append(f"{mid}: gated or token-requiring models are excluded")
        for f in m["files"]:
            path = str(f.get("path", ""))
            if not path or path.startswith("/") or ".." in path.split("/") or "\\" in path:
                errors.append(f"{mid}: unsafe file path")
            if not isinstance(f.get("bytes"), int) or f["bytes"] <= 0:
                errors.append(f"{mid}: {path}: bytes must be positive")
            has_sha, has_blob = "sha256" in f, "git_blob_sha1" in f
            if has_sha == has_blob or (has_sha and not _HEX64.match(f["sha256"])) \
                    or (has_blob and not _HEX40.match(f["git_blob_sha1"])):
                errors.append(f"{mid}: {path}: exactly one valid sha256 or git_blob_sha1 is required")
    for role in ROLES:
        if sum(1 for m in models if m.get("role") == role) != 1:
            errors.append(f"exactly one model must hold role {role}")
    return errors


def load_manifest(path: Path = MANIFEST_PATH) -> Dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(manifest)
    if errors:
        raise config.RuntimeConfigError("invalid SER manifest: " + "; ".join(errors))
    return manifest


def get(manifest: Mapping[str, Any], logical_id: str) -> Dict[str, Any]:
    for m in manifest["models"]:
        if m["logical_id"] == logical_id:
            return dict(m)
    raise config.RuntimeConfigError(f"unknown SER model {logical_id!r}")


def model_dir(root: Path, entry: Mapping[str, Any]) -> Path:
    return config.confined(root, entry["logical_id"], entry["revision"])


def plan(root: Path, manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for m in manifest["models"]:
        target = model_dir(root, m)
        check = config.verify_files(target, m["files"], full_hash=False)
        rows.append({"model": m["logical_id"], "role": m["role"], "revision": m["revision"],
                     "bytes": sum(f["bytes"] for f in m["files"]), "destination": config.label(target, root),
                     "present_by_size": check["ok"]})
    return rows


def verify(root: Path, entry: Mapping[str, Any]) -> Dict[str, Any]:
    check = config.verify_files(model_dir(root, entry), entry["files"], full_hash=True)
    return {"model": entry["logical_id"], "ok": check["ok"], "bytes": check["bytes"],
            **{k: check[k] for k in ("missing", "size_mismatch", "hash_mismatch")}}


def fetch(root: Path, entry: Mapping[str, Any]) -> Dict[str, Any]:
    target = model_dir(root, entry)
    existing = config.verify_files(target, entry["files"], full_hash=True)
    if existing["ok"]:
        return {"model": entry["logical_id"], "result": "already_present_and_verified", "bytes": existing["bytes"]}
    need = sum(f["bytes"] for f in entry["files"])
    free = free_bytes(root)
    if free is not None and free < need + DISK_MARGIN_BYTES:
        return {"model": entry["logical_id"], "result": "refused_insufficient_disk", "free_mib": free // 2**20}
    _hf_env(root)
    hub = importlib.import_module("huggingface_hub")
    target.mkdir(parents=True, exist_ok=True)
    hub.snapshot_download(repo_id=entry["upstream_repo"], revision=entry["revision"],
                          allow_patterns=[f["path"] for f in entry["files"]], local_dir=str(target), token=False)
    result = verify(root, entry)
    result["result"] = "downloaded_and_verified" if result["ok"] else "integrity_failed"
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.ser.models", description=__doc__.split("\n")[0])
    parser.add_argument("--models-root", default=None, help="defaults to SAHAY_MODELS_ROOT")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="pinned files, sizes and destinations; no network")
    f = sub.add_parser("fetch", help="download and verify pinned files (network)")
    f.add_argument("--model", required=True)
    sub.add_parser("verify", help="full hash verification of every SER model; no network")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    root = config.models_root(args.models_root)
    if args.cmd == "plan":
        out: Any = plan(root, manifest)
    elif args.cmd == "verify":
        out = [verify(root, m) for m in manifest["models"]]
    else:
        ids = [m["logical_id"] for m in manifest["models"]] if args.model == "all" else [args.model]
        out = [fetch(root, get(manifest, i)) for i in ids]
    print(json.dumps(out, indent=1))
    rows = out if isinstance(out, list) else [out]
    return 0 if all(r.get("ok", True) and r.get("result", "ok") not in ("integrity_failed", "refused_insufficient_disk")
                    for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
