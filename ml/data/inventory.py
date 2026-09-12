"""Non-extracting inventory of the external dataset root. Standard library only.

    python -m ml.data.inventory                               # root from SAHAY_DATASETS_ROOT
    python -m ml.data.inventory --root <dataset-root> --exclude-pattern <regex> [--exclude-pattern ...]

Walks the root recursively and records, per file: relative path, byte size,
extension and SHA-256. For every ZIP it runs the existing central-directory
checks (``archive_safety.inspect_zip``); for every CSV it reads the HEADER LINE
ONLY and keeps the column names if, and only if, they look like column names;
for tiny files it tests (as a boolean) whether they are Git LFS pointer stubs.
It never extracts, never reads a ZIP member, never reads a data row, and never
prints or writes file contents.

``--exclude-pattern`` (a regular expression, case-insensitive, matched against
each relative path and each directory name) removes paths that are out of scope
for the current task BEFORE they are opened, hashed or listed. Excluded paths
are not counted or named anywhere.

Output goes to ``<SAHAY_DATASETS_ROOT>/reports/inventory/`` — beneath the
private root, never inside a SAHAY checkout: a JSON file with one row per
file, labelled with ``<SAHAY_DATASETS_ROOT>`` rather than a machine path, and a
Markdown summary with aggregates only. The tool-owned ``reports/`` and
``normalized/`` directories are never inventoried themselves.

Exit codes: 0 written; 4 configuration error (no root, bad pattern).
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import archive_safety as az
from . import governance as gov

REPO = Path(__file__).resolve().parents[2]
ROOT_LABEL = "<" + gov.ROOT_ENV + ">"
#: Top-level directories this tooling writes into the root; never inventoried.
TOOL_OWNED = ("reports", "normalized")
LFS_SIGNATURE = b"version https://git-lfs."
LFS_MAX_BYTES = 1024
HEADER_MAX_BYTES = 8192
EXIT_OK, EXIT_CONFIG = 0, 4


def looks_like_header(fields: Sequence[str]) -> bool:
    """True when every field is short and none reads like a sentence.

    A header-less CSV puts a real record on line one; this refuses to keep it.
    """
    if not fields:
        return False
    for field in fields:
        value = field.strip()
        if len(value) > 40:
            return False
        if " " in value and any(ch in value for ch in ".!?,"):
            return False
    return True


def csv_columns(path: Path) -> Dict[str, Any]:
    """Column names from the header line only, or a withheld marker."""
    with open(path, "rb") as fh:
        first = fh.readline(HEADER_MAX_BYTES)
    try:
        line = first.decode("utf-8-sig")
        encoding = "utf-8"
    except UnicodeDecodeError:
        line = first.decode("latin-1")
        encoding = "not_utf-8"
    fields = next(csv.reader(io.StringIO(line)), [])
    if looks_like_header(fields):
        return {"header": "columns", "encoding": encoding, "columns": [f.strip() for f in fields]}
    return {"header": "withheld", "encoding": encoding, "field_count": len(fields),
            "reason": "the first line does not look like column names, so it may be a data row"}


def is_lfs_pointer(path: Path, size: int) -> bool:
    if size > LFS_MAX_BYTES:
        return False
    with open(path, "rb") as fh:
        return fh.read(len(LFS_SIGNATURE)) == LFS_SIGNATURE


MEDIA_EXTENSIONS = frozenset({".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus", ".aac", ".flv", ".mp4",
                              ".avi", ".mkv", ".webm"})


def media_availability(report: Dict[str, Any], top_level: str) -> Dict[str, Any]:
    """Real versus placeholder media under one top-level entry of an inventory.

    A Git LFS pointer stub is a small text file standing in for a media file;
    it is never counted as audio or video.
    """
    rows = [r for r in report["files"]
            if r["relative_path"].split("/")[0] == top_level and r.get("extension") in MEDIA_EXTENSIONS]
    stubs = sum(1 for r in rows if r.get("git_lfs_pointer"))
    real = len(rows) - stubs
    return {"top_level": top_level, "media_files": len(rows), "git_lfs_pointer_stubs": stubs,
            "real_media_files": real, "available": real > 0,
            "statement": "no real media is present; acoustic processing is unavailable" if real == 0
            else f"{real} real media file(s) present"}


def build(root: Path, excludes: Sequence["re.Pattern[str]"] = (),
          registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    reg = registry if registry is not None else gov.load_registry()
    by_sha = {r["sha256"]: r["id"] for r in reg["datasets"] if r.get("sha256")}
    by_path = {r["local_relative_path"]: r["id"] for r in reg["datasets"] if r.get("local_relative_path")}

    def excluded(rel: str) -> bool:
        if rel.split("/")[0] in TOOL_OWNED:
            return True
        return any(p.search(rel) for p in excludes)

    root = Path(root).resolve()
    rows: List[Dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        dirnames[:] = sorted(d for d in dirnames if not excluded(f"{rel_dir}/{d}".lstrip("/")))
        for name in sorted(filenames):
            rel = f"{rel_dir}/{name}".lstrip("/")
            if excluded(rel):
                continue
            path = gov.resolve_under(root, rel)
            if path.is_symlink():
                rows.append({"relative_path": rel, "kind": "symlink_not_followed"})
                continue
            size = path.stat().st_size
            digest = az.sha256_file(path)
            row: Dict[str, Any] = {"relative_path": rel, "bytes": size, "extension": path.suffix.lower() or "<none>",
                                   "sha256": digest,
                                   "registered_as": by_sha.get(digest) or by_path.get(rel)}
            if row["registered_as"] and by_path.get(rel) and by_sha.get(digest) != by_path.get(rel):
                row["registry_hash_mismatch"] = True
            if is_lfs_pointer(path, size):
                row["git_lfs_pointer"] = True
            if zipfile.is_zipfile(path):
                row["zip"] = az.inspect_zip(path)
            elif row["extension"] in (".csv", ".tsv"):
                row["csv"] = csv_columns(path)
            rows.append(row)
    return {"report": "sahay-external-dataset-inventory", "root": ROOT_LABEL, "files": rows,
            "summary": summarise(rows),
            "note": "Metadata only: relative paths, sizes, hashes, ZIP directory findings and CSV column names. "
                    "No member name, data row or content is recorded. Never commit this file."}


def summarise(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    tops: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        top = r["relative_path"].split("/")[0]
        t = tops.setdefault(top, {"files": 0, "bytes": 0, "extensions": {}, "zips": 0, "unsafe_zips": 0,
                                  "git_lfs_pointers": 0, "registered": set(), "unregistered_files": 0})
        t["files"] += 1
        t["bytes"] += r.get("bytes", 0)
        ext = r.get("extension", "<none>")
        t["extensions"][ext] = t["extensions"].get(ext, 0) + 1
        if "zip" in r:
            t["zips"] += 1
            t["unsafe_zips"] += not r["zip"]["safe"]
        t["git_lfs_pointers"] += bool(r.get("git_lfs_pointer"))
        if r.get("registered_as"):
            t["registered"].add(r["registered_as"])
        else:
            t["unregistered_files"] += 1
    for t in tops.values():
        t["registered"] = sorted(t["registered"])
        t["extensions"] = dict(sorted(t["extensions"].items(), key=lambda kv: (-kv[1], kv[0])))
    return {"files": len(rows), "bytes": sum(r.get("bytes", 0) for r in rows),
            "zips": sum(1 for r in rows if "zip" in r),
            "unsafe_zips": sum(1 for r in rows if "zip" in r and not r["zip"]["safe"]),
            "git_lfs_pointers": sum(1 for r in rows if r.get("git_lfs_pointer")),
            "by_top_level": dict(sorted(tops.items()))}


def render(report: Dict[str, Any]) -> str:
    s = report["summary"]
    out = ["# External dataset inventory (local, never committed)", "",
           f"Root: `{report['root']}` · {s['files']} files · {s['bytes']:,} bytes · {s['zips']} ZIP archive(s), "
           f"{s['unsafe_zips']} unsafe · {s['git_lfs_pointers']} Git LFS pointer stub(s)", "",
           "| Top-level entry | Files | Bytes | Extensions | ZIPs | LFS stubs | Registered as | Unregistered files |",
           "|---|---:|---:|---|---:|---:|---|---:|"]
    for top, t in s["by_top_level"].items():
        ext = ", ".join(f"{k}:{v}" for k, v in list(t["extensions"].items())[:6])
        out.append(f"| `{top}` | {t['files']} | {t['bytes']:,} | {ext} | {t['zips']} | {t['git_lfs_pointers']} | "
                   f"{', '.join(t['registered']) or '—'} | {t['unregistered_files']} |")
    out += ["", "## ZIP central-directory findings", ""]
    zips = [r for r in report["files"] if "zip" in r]
    if not zips:
        out.append("No ZIP archive is present under the root.")
    for r in zips:
        z = r["zip"]
        out.append(f"- `{r['relative_path']}`: {z.get('members')} members, declared {z.get('declared_uncompressed_bytes')} "
                   f"bytes, overall ratio {z.get('overall_ratio')}, findings {z.get('findings') or 'none'}")
    out += ["", report["note"], ""]
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SAHAY-AI non-extracting dataset inventory (metadata only)")
    parser.add_argument("--root", default=None, help=f"dataset root (default: ${gov.ROOT_ENV})")
    parser.add_argument("--out", default=None, help="default: <root>/reports/inventory")
    parser.add_argument("--exclude-pattern", action="append", default=[], metavar="REGEX",
                        help="exclude matching relative paths before they are opened (repeatable)")
    args = parser.parse_args(argv)
    try:
        root = gov.dataset_root(args.root)
        patterns = [re.compile(p, re.IGNORECASE) for p in args.exclude_pattern]
    except gov.DatasetRootError as exc:
        print(f"configuration: {exc}")
        return EXIT_CONFIG
    except re.error:
        print("configuration: an --exclude-pattern is not a valid regular expression")
        return EXIT_CONFIG
    from .external_corpus import inside_sahay_worktree, reports_dir  # local: keeps import time small
    out = Path(args.out) if args.out else reports_dir(root, "inventory")
    if inside_sahay_worktree(out):
        print("configuration: refusing to write an inventory inside a SAHAY Git worktree")
        return EXIT_CONFIG
    report = build(root, patterns)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in (("inventory.json", json.dumps(report, indent=1, ensure_ascii=False) + "\n"),
                       ("inventory.md", render(report))):
        tmp = out / (name + ".partial")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, out / name)
    s = report["summary"]
    print(f"inventory: {s['files']} files, {s['zips']} ZIP(s) ({s['unsafe_zips']} unsafe), "
          f"{s['git_lfs_pointers']} LFS stub(s); written to the private reports directory")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
