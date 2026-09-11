"""Untrusted-archive safety checks. Standard library only.

Reads only the ZIP central directory (names, sizes, flags). It never reads
member bytes, never prints member names in reports (only counts, extensions
and depth), never executes anything and never opens audio.

What directory metadata can and cannot establish: it can show that no member
has an unsafe name or attribute (absolute or traversal path, device name,
alternate data stream, duplicate, encryption flag, symlink attribute) and
that no member has an executable-LOOKING or archive-looking file extension.
It cannot prove that member BYTES are non-executable or free of embedded
content, because member contents are not inspected. Reports say "executable-
looking member names", never "no executable content".

Extraction (`safe_extract`) is a separate, explicit step that re-checks
every member and writes only beneath a destination the caller has already
confined to the dataset root.
"""

import hashlib
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List

#: Defaults. A caller may lower them; raising them is a governance decision.
MAX_TOTAL_UNCOMPRESSED = 2 * 1024 ** 3   # 2 GiB declared expansion ceiling
MAX_MEMBER_RATIO = 100.0                  # compression ratio per member
MAX_OVERALL_RATIO = 50.0                  # compression ratio for the archive
MAX_MEMBERS = 200_000

ARCHIVE_EXTENSIONS = frozenset({".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".zst"})
AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus", ".aac", ".wma", ".webm"})
#: Extensions that make a member NAME look executable. A name check only; the
#: bytes of a member are never read, so this proves nothing about its content.
EXECUTABLE_EXTENSIONS = frozenset({".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh", ".com", ".scr", ".msi",
                                   ".vbs", ".js", ".jar", ".py", ".pyc", ".so", ".dylib", ".lnk"})
_DEVICE_NAMES = frozenset({"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                           *(f"lpt{i}" for i in range(1, 10))})


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def member_problems(name: str) -> List[str]:
    """Why a single member name is unsafe (empty list = safe)."""
    problems = []
    raw = name.replace("\\", "/")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":") or raw.startswith("//"):
        problems.append("absolute_path")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        problems.append("path_traversal")
    if any(":" in p for p in parts if not (len(p) == 2 and p[1] == ":")):
        problems.append("alternate_data_stream_or_drive")
    if any(p.split(".")[0].casefold() in _DEVICE_NAMES for p in parts):
        problems.append("device_name")
    if any(ord(c) < 32 for c in raw):
        problems.append("control_character")
    return problems


def inspect_zip(path: Path, *, max_total: int = MAX_TOTAL_UNCOMPRESSED, max_member_ratio: float = MAX_MEMBER_RATIO,
                max_overall_ratio: float = MAX_OVERALL_RATIO, max_members: int = MAX_MEMBERS) -> Dict[str, Any]:
    """Central-directory inspection. Returns counts and findings, never names or content."""
    findings: List[str] = []
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return {"format": "not_a_zip", "safe": False, "findings": ["not_a_valid_zip"]}
    with zf:
        infos = zf.infolist()
    files = [i for i in infos if not i.is_dir()]
    names = [i.filename for i in infos]
    per_problem: Dict[str, int] = {}
    for n in names:
        for p in member_problems(n):
            per_problem[p] = per_problem.get(p, 0) + 1
    folded = [PurePosixPath(n.replace("\\", "/")).as_posix().rstrip("/").casefold() for n in names]
    duplicates = len(folded) - len(set(folded))
    encrypted = sum(1 for i in files if i.flag_bits & 0x1)
    symlinks = sum(1 for i in files if stat.S_ISLNK(i.external_attr >> 16))
    ext = {}
    for i in files:
        e = os.path.splitext(i.filename)[1].lower() or "<none>"
        ext[e] = ext.get(e, 0) + 1
    nested = sum(n for e, n in ext.items() if e in ARCHIVE_EXTENSIONS)
    executable_names = sum(n for e, n in ext.items() if e in EXECUTABLE_EXTENSIONS)
    audio = sum(n for e, n in ext.items() if e in AUDIO_EXTENSIONS)
    compressed = sum(i.compress_size for i in files)
    uncompressed = sum(i.file_size for i in files)
    member_ratios = [i.file_size / i.compress_size for i in files if i.compress_size]
    max_ratio = max(member_ratios, default=0.0)
    overall = (uncompressed / compressed) if compressed else 0.0
    depth = max((n.replace("\\", "/").rstrip("/").count("/") for n in names), default=0)

    for problem, count in sorted(per_problem.items()):
        findings.append(f"{problem}:{count}")
    if duplicates:
        findings.append(f"duplicate_member_names:{duplicates}")
    if encrypted:
        findings.append(f"encrypted_members:{encrypted}")
    if symlinks:
        findings.append(f"symlink_members:{symlinks}")
    if nested:
        findings.append(f"nested_archives_unsupported:{nested}")
    if executable_names:
        findings.append(f"executable_looking_member_names:{executable_names}")
    if len(infos) > max_members:
        findings.append(f"too_many_members:{len(infos)}")
    if uncompressed > max_total:
        findings.append("declared_size_exceeds_ceiling")
    if max_ratio > max_member_ratio:
        findings.append("suspicious_member_compression_ratio")
    if overall > max_overall_ratio:
        findings.append("suspicious_overall_compression_ratio")
    return {
        "format": "zip",
        "members": len(infos), "files": len(files), "directories": len(infos) - len(files),
        "max_depth": depth,
        "extensions": dict(sorted(ext.items())),
        "audio_members": audio,
        "scope": "central-directory metadata only; member contents were not inspected",
        "compressed_bytes": compressed, "declared_uncompressed_bytes": uncompressed,
        "overall_ratio": round(overall, 3), "max_member_ratio": round(max_ratio, 3),
        "extraction_ceiling_bytes": max_total,
        "findings": findings,
        "safe": not findings,
    }


class UnsafeArchive(Exception):
    pass


def safe_extract(path: Path, destination: Path, *, max_total: int = MAX_TOTAL_UNCOMPRESSED) -> Dict[str, Any]:
    """Extract only if every check passes. `destination` must not exist yet or be empty.

    Members are written one by one, by resolved path checked to stay inside the
    working directory; the running total is capped at `max_total` regardless of
    the sizes the archive declares.

    All-or-nothing: members are written into a temporary sibling directory and
    moved into `destination` only after the last member succeeds. If anything
    fails — a member that escapes, a size ceiling crossed mid-stream because
    the archive under-declared its sizes, an attempted overwrite, an I/O error —
    the temporary directory is removed and `destination` is left exactly as it
    was. No partial extraction is ever presented as a result.
    """
    report = inspect_zip(path, max_total=max_total)
    if not report["safe"]:
        raise UnsafeArchive("archive failed safety checks: " + ", ".join(report["findings"]))
    destination = Path(destination)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise UnsafeArchive("destination is not empty")
    work = destination.with_name(f".{destination.name}.partial-{os.getpid()}")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    root = work.resolve()
    written = 0
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                target = (root / info.filename.replace("\\", "/")).resolve()
                if root != target and root not in target.parents:
                    raise UnsafeArchive("member escapes destination")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if target.exists():
                    raise UnsafeArchive("member would overwrite an existing file")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "xb") as dst:
                    while True:
                        block = src.read(1 << 20)
                        if not block:
                            break
                        written += len(block)
                        if written > max_total:
                            raise UnsafeArchive("extraction exceeded the size ceiling")
                        dst.write(block)
        if destination.exists():
            destination.rmdir()  # empty, checked above
        os.replace(work, destination)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return {"extracted_bytes": written, "members": report["members"]}
