"""Explicit, pinned model download and local Whisper conversion. Never runs on import or in tests.

    python -m ml.runtime.download plan
    python -m ml.runtime.download fetch --model all
    python -m ml.runtime.download convert-whisper

``fetch`` downloads only the files the manifest lists, at the manifest's immutable revision,
anonymously (``token=False``), into ``<SAHAY_MODELS_ROOT>/<logical_id>/<revision>/``, with the
Hugging Face cache redirected beneath the same root. It checks free disk space first and
verifies every file's size and upstream hash afterwards. ``convert-whisper`` converts the
verified Whisper revision to CTranslate2 FP16 for faster-whisper and records a private hash
inventory beside it. Output is aggregate only: no absolute path, no token.
"""

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from . import config, device as dev
from .status import RuntimeFailure

DISK_MARGIN_BYTES = 2 * 2**30


def _hf_env(root: Path) -> None:
    os.environ["HF_HOME"] = str(config.confined(root, ".hf-home"))
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ.pop(key, None)


def free_bytes(path: Path) -> Optional[int]:
    if not dev.package_available("psutil"):
        return None
    return importlib.import_module("psutil").disk_usage(str(path)).free


def plan(root: Path, manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for entry in manifest["models"]:
        if entry["source"] != "huggingface":
            continue
        target = config.model_dir(root, entry)
        check = config.verify_files(target, entry["files"], full_hash=False)
        rows.append({"model": entry["logical_id"], "repo": entry["upstream_repo"], "revision": entry["revision"],
                     "files": len(entry["files"]), "bytes": sum(f["bytes"] for f in entry["files"]),
                     "destination": config.label(target, root), "present_by_size": check["ok"]})
    return rows


def fetch(root: Path, entry: Mapping[str, Any]) -> Dict[str, Any]:
    if entry["source"] != "huggingface":
        raise RuntimeFailure("invalid_input", "only Hugging Face models are fetched; Silero ships in its wheel")
    if entry["gated"] or entry["token_required"]:
        raise RuntimeFailure("invalid_input", "gated or token-requiring models are excluded")
    target = config.model_dir(root, entry)
    existing = config.verify_files(target, entry["files"], full_hash=True)
    if existing["ok"]:
        return {"model": entry["logical_id"], "result": "already_present_and_verified", "bytes": existing["bytes"]}
    need = sum(f["bytes"] for f in entry["files"])
    free = free_bytes(root)
    if free is not None and free < need + DISK_MARGIN_BYTES:
        raise RuntimeFailure("invalid_input", f"not enough free disk space ({free // 2**20} MiB free)")
    _hf_env(root)
    hub = importlib.import_module("huggingface_hub")
    target.mkdir(parents=True, exist_ok=True)
    hub.snapshot_download(repo_id=entry["upstream_repo"], revision=entry["revision"],
                          allow_patterns=[f["path"] for f in entry["files"]], local_dir=str(target), token=False)
    check = config.verify_files(target, entry["files"], full_hash=True)
    if not check["ok"]:
        raise RuntimeFailure("integrity_failed", json.dumps({k: check[k] for k in
                                                            ("missing", "size_mismatch", "hash_mismatch")}))
    return {"model": entry["logical_id"], "result": "downloaded_and_verified", "bytes": check["bytes"],
            "files": check["checked"]}


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        child.rmdir() if child.is_dir() else child.unlink()
    path.rmdir()


def convert_whisper(root: Path, entry: Mapping[str, Any]) -> Dict[str, Any]:
    source = config.model_dir(root, entry)
    check = config.verify_files(source, entry["files"], full_hash=True)
    if not check["ok"]:
        raise RuntimeFailure("integrity_failed", "the pinned Whisper files are missing or do not match")
    derived = entry["derived"]
    out = config.derived_dir(root, entry)
    record_path = out / "conversion.json"
    if record_path.is_file():
        return {"model": entry["logical_id"], "result": "already_converted",
                "derived": config.label(out, root)}
    partial = out.with_name(out.name + ".partial")
    _remove_tree(partial)
    ct2 = importlib.import_module("ctranslate2")
    converter = ct2.converters.TransformersConverter(str(source), copy_files=list(derived["copy_files"]),
                                                     low_cpu_mem_usage=True)
    converter.convert(str(partial), quantization=derived["quantization"], force=True)
    _remove_tree(out)
    os.replace(partial, out)
    rows = config.inventory(out, root)
    record = {"source_repo": entry["upstream_repo"], "source_revision": entry["revision"], "tool": derived["tool"],
              "ctranslate2": ct2.__version__, "transformers": importlib.import_module("transformers").__version__,
              "quantization": derived["quantization"], "files": rows, "bytes": sum(r["bytes"] for r in rows)}
    record_path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return {"model": entry["logical_id"], "result": "converted", "derived": config.label(out, root),
            "files": len(rows), "bytes": record["bytes"]}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.runtime.download", description=__doc__.split("\n")[0])
    parser.add_argument("--models-root", help=f"overrides {config.ROOT_ENV}; there is no default")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="show pinned files, sizes and destinations; no network")
    p = sub.add_parser("fetch", help="download and verify pinned files")
    p.add_argument("--model", default="all")
    sub.add_parser("convert-whisper", help="convert the verified Whisper revision to CTranslate2 FP16")
    args = parser.parse_args(argv)
    try:
        root = config.models_root(args.models_root)
        manifest = config.load_manifest()
        if args.command == "plan":
            rows = plan(root, manifest)
            print(json.dumps({"models": rows, "total_bytes": sum(r["bytes"] for r in rows),
                              "free_bytes": free_bytes(root)}, indent=1))
        elif args.command == "fetch":
            ids = [m["logical_id"] for m in manifest["models"] if m["source"] == "huggingface"]
            chosen = ids if args.model == "all" else [args.model]
            for logical_id in chosen:
                print(json.dumps(fetch(root, config.get_model(manifest, logical_id))))
        else:
            print(json.dumps(convert_whisper(root, config.get_model(manifest, "whisper_small"))))
    except (config.RuntimeConfigError, RuntimeFailure) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
