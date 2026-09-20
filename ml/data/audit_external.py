"""External-dataset audit. Standard library only; offline; never prints content.

    python -m ml.data.audit_external                       # root from SAHAY_DATASETS_ROOT
    python -m ml.data.audit_external --root <dataset-root>         # explicit root
    python -m ml.data.audit_external --out runtime/dataset-audit

    # extraction is separate, explicit, and refused unless every gate passes:
    python -m ml.data.audit_external --extract emoinhindi

For every registered DOWNLOADED dataset it resolves the file strictly beneath
the dataset root, hashes it, compares size and SHA-256 with the registry,
inspects the ZIP central directory (never member bytes) and reports
governance gaps. Reports hold counts, extensions and findings only: no member
names, no sample text, no absolute path.

Exit codes:
  0  every downloaded dataset matches, is safe and is approved
  2  integrity mismatch, missing file, unsafe archive, or a file that
     resolves outside the root at run time (takes precedence over 3)
  3  integrity and safety fine, but governance/licence approval is missing
  4  configuration error: no or non-existent dataset root, registry missing,
     malformed or invalid (including an unsafe relative path in a record)

The registry is never modified. A human updates it in a reviewed change.
"""

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import archive_safety as az
from . import governance as gov

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "runtime" / "dataset-audit"
EXIT_OK, EXIT_INTEGRITY, EXIT_GOVERNANCE, EXIT_CONFIG = 0, 2, 3, 4
ROOT_LABEL = "<" + gov.ROOT_ENV + ">"


def archive_check(path: Path, rec: Dict[str, Any]) -> Dict[str, Any]:
    """Archive safety for one registered file.

    A file that IS a ZIP is always inspected, whatever the registry claims, so a
    ZIP renamed to .csv cannot slip past. A file that is NOT a ZIP counts as
    "not an archive" only when the registry explicitly records
    ``archive_safety_status: not_applicable`` for it (a loose file such as an
    already-extracted CSV). A registry that expects an archive but finds a
    non-ZIP is still reported as unsafe: that mismatch needs a human.
    """
    if zipfile.is_zipfile(path):
        return az.inspect_zip(path)
    if rec.get("archive_safety_status") == "not_applicable":
        return {"format": "not_an_archive", "safe": True, "findings": [],
                "scope": "loose file registered as not an archive; no archive checks apply, integrity still checked"}
    return az.inspect_zip(path)


def audit(reg: Dict[str, Any], root: Path) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for rec in reg["datasets"]:
        row: Dict[str, Any] = {"id": rec["id"], "download_status": rec["download_status"],
                               "review_status": rec["review_status"], "governance_gaps": gov.governance_gaps(rec)}
        if rec["download_status"] != "downloaded":
            row["status"] = "not_downloaded"
            rows.append(row)
            continue
        row["relative_path"] = ROOT_LABEL + "/" + rec["local_relative_path"]
        try:
            path = gov.resolve_under(root, rec["local_relative_path"])
        except gov.DatasetRootError as exc:
            row.update(status="unsafe_path", detail=str(exc))
            rows.append(row)
            continue
        if not path.is_file():
            row.update(status="missing_file")
            rows.append(row)
            continue
        size = path.stat().st_size
        digest = az.sha256_file(path)
        row.update(expected_bytes=rec["byte_size"], actual_bytes=size, size_match=size == rec["byte_size"],
                   expected_sha256=rec["sha256"], actual_sha256=digest, sha256_match=digest == rec["sha256"])
        row["archive"] = archive_check(path, rec)
        if not (row["size_match"] and row["sha256_match"]):
            row["status"] = "integrity_mismatch"
        elif not row["archive"]["safe"]:
            row["status"] = "unsafe_archive"
        elif not rec["review_status"].startswith("approved_"):
            row["status"] = "governance_pending"
        else:
            row["status"] = "ok"
        rows.append(row)
    statuses = [r["status"] for r in rows]
    if any(s in ("integrity_mismatch", "unsafe_archive", "missing_file", "unsafe_path") for s in statuses):
        code = EXIT_INTEGRITY
    elif any(s == "governance_pending" for s in statuses):
        code = EXIT_GOVERNANCE
    else:
        code = EXIT_OK
    return {"report": "sahay-external-dataset-audit", "root": ROOT_LABEL,
            "registry_schema_version": reg["schema_version"], "datasets": rows, "exit_code": code,
            "note": "Metadata only. No member names, sample text or absolute paths are recorded. "
                    "The registry was not modified."}


def render(report: Dict[str, Any]) -> str:
    out = ["# External dataset audit", "",
           f"Dataset root: `{report['root']}` · exit code {report['exit_code']}", "",
           "| Dataset | Download | Review state | Status | Size match | SHA-256 match | Archive findings |",
           "|---|---|---|---|---|---|---|"]
    for r in report["datasets"]:
        arch = r.get("archive") or {}
        findings = ", ".join(arch.get("findings") or []) or ("none" if arch else "—")
        out.append(f"| `{r['id']}` | {r['download_status']} | {r['review_status']} | {r['status']} | "
                   f"{r.get('size_match', '—')} | {r.get('sha256_match', '—')} | {findings} |")
    out += ["", "## Archive metadata (counts only)", ""]
    for r in report["datasets"]:
        a = r.get("archive")
        if a and a.get("format") == "zip":
            out.append(f"- `{r['id']}`: {a['members']} members ({a['files']} files), extensions {a['extensions']}, "
                       f"audio members {a['audio_members']}, declared {a['declared_uncompressed_bytes']} bytes, "
                       f"overall ratio {a['overall_ratio']}, max member ratio {a['max_member_ratio']}.")
    out += ["", "Scope: central-directory metadata only. A pass means no unsafe member name or attribute and no "
            "executable- or archive-looking member name; member contents were not inspected, so it does not "
            "prove the contents are non-executable or free of personal data.", "",
            "## Governance gaps (not auto-fixed)", ""]
    for r in report["datasets"]:
        out.append(f"- `{r['id']}`: {', '.join(r['governance_gaps']) or 'none'}")
    out += ["", report["note"]]
    return "\n".join(out) + "\n"


def write_reports(report: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "audit.json").write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                                        encoding="utf-8", newline="\n")
    (out_dir / "audit.md").write_text(render(report), encoding="utf-8", newline="\n")


def extract(reg: Dict[str, Any], root: Path, dataset_id: str) -> Dict[str, Any]:
    """Extract one dataset only if integrity, safety and licence gates all pass."""
    rec = gov.get(reg, dataset_id)
    if rec["download_status"] != "downloaded":
        raise gov.GovernanceError(f"{dataset_id} is not downloaded")
    gov.select_for(reg, dataset_id, "research")  # licence_pending/quarantined datasets are refused here
    src = gov.resolve_under(root, rec["local_relative_path"])
    if az.sha256_file(src) != rec["sha256"] or src.stat().st_size != rec["byte_size"]:
        raise az.UnsafeArchive("integrity mismatch; refusing to extract")
    dest = gov.resolve_under(root, f"extracted/{dataset_id}/{rec['sha256'][:12]}")
    if REPO == dest or REPO in dest.parents:
        raise gov.DatasetRootError("refusing to extract inside the Git worktree")
    return az.safe_extract(src, dest)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SAHAY-AI external dataset audit (metadata only)")
    parser.add_argument("--root", default=None, help=f"dataset root (default: ${gov.ROOT_ENV})")
    parser.add_argument("--registry", default=str(gov.REGISTRY_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--extract", default=None, metavar="DATASET_ID",
                        help="extract one dataset after every gate passes (never by default)")
    args = parser.parse_args(argv)

    try:
        reg = gov.load_registry(Path(args.registry))
    except (OSError, ValueError) as exc:  # missing, unreadable or malformed JSON
        print(f"configuration: registry could not be read ({type(exc).__name__})")
        return EXIT_CONFIG
    try:
        problems = gov.validate_registry(reg)
        if problems:
            print("registry invalid: " + "; ".join(problems[:5]))
            return EXIT_CONFIG
        root = gov.dataset_root(args.root)
    except gov.DatasetRootError as exc:
        print(f"configuration: {exc}")
        return EXIT_CONFIG

    if args.extract:
        try:
            result = extract(reg, root, args.extract)
        except (gov.GovernanceError, gov.DatasetRootError, az.UnsafeArchive) as exc:
            print(f"extraction refused: {exc}")
            return EXIT_GOVERNANCE if isinstance(exc, gov.GovernanceError) else EXIT_INTEGRITY
        print(f"extracted {result['members']} members ({result['extracted_bytes']} bytes) for {args.extract}")
        return EXIT_OK

    report = audit(reg, root)
    write_reports(report, Path(args.out))
    for r in report["datasets"]:
        print(f"{r['id']}: {r['status']} (review: {r['review_status']})")
    print(f"reports written to {Path(args.out).name}/ ; exit code {report['exit_code']}")
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
