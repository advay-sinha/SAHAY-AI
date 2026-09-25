"""SER training audio: RAVDESS fetch and extraction, CREMA-D integrity check (plan M12b, run R1).

    python -m ml.data.ser_audio status
    python -m ml.data.ser_audio snapshot-crema-pointers  # no network; run BEFORE fetching CREMA-D audio
    python -m ml.data.ser_audio fetch-ravdess            # network: Zenodo record 1188976, one file
    python -m ml.data.ser_audio verify-crema             # no network; after the AudioWAV download

Approvals: EXT-003 (RAVDESS, Audio_Speech_Actors_01-24.zip only) and EXT-104 (CREMA-D, AudioWAV
only). The owner runs these commands by hand. All files stay beneath ``SAHAY_DATASETS_ROOT``,
never in Git. Reports contain counts and hashes only: no member names, no audio and no
absolute path.

A dataset only becomes usable for training after this check passes AND its registry record is
updated to ``approved_for_training`` in a reviewed change. Download alone never approves anything.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import archive_safety, governance

RAVDESS = {
    "dataset_id": "ravdess_audio_speech",
    "url": "https://zenodo.org/api/records/1188976/files/Audio_Speech_Actors_01-24.zip/content",
    "relative_dir": "corpus/audio/ravdess",
    "filename": "Audio_Speech_Actors_01-24.zip",
    "bytes": 208468073,
    "md5": "bc696df654c87fed845eb13823edef8a",
    "expected_wav": 1440,
}
CREMA = {
    "dataset_id": "crema_d",
    # The existing local copy is an extracted repository archive: every AudioWAV entry is a Git LFS
    # pointer (oid sha256 + size). Those pointers are the integrity reference for the real audio.
    "pointer_dir": "CREMA-D-1.0/CREMA-D-1.0/AudioWAV",
    "pointer_manifest": "corpus/audio/crema_d/pointer-manifest.json",
    # Where the real audio lands (fresh sparse clone + `git lfs pull`, or an approved mirror).
    "audio_dir": "corpus/audio/crema_d/CREMA-D/AudioWAV",
    "expected_wav": 7442,
    "expected_bytes": 605899936,  # sum of the LFS pointer sizes, measured 2026-09-24
}
_CHUNK = 1 << 20


def _hashes(path: Path) -> Dict[str, str]:
    md5, sha = hashlib.md5(), hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            md5.update(block)
            sha.update(block)
    return {"md5": md5.hexdigest(), "sha256": sha.hexdigest()}


def ravdess_paths(root: Path) -> Dict[str, Path]:
    base = governance.resolve_under(root, RAVDESS["relative_dir"])
    return {"base": base, "zip": base / RAVDESS["filename"], "extracted": base / "extracted"}


def fetch_ravdess(root: Path) -> Dict[str, Any]:
    paths = ravdess_paths(root)
    paths["base"].mkdir(parents=True, exist_ok=True)
    target = paths["zip"]
    if not (target.is_file() and target.stat().st_size == RAVDESS["bytes"]):
        import urllib.request  # the only network use in this module, reached only by this command
        partial = target.with_suffix(".part")
        with urllib.request.urlopen(RAVDESS["url"], timeout=60) as resp, open(partial, "wb") as out:
            while True:
                block = resp.read(_CHUNK)
                if not block:
                    break
                out.write(block)
        partial.replace(target)
    size = target.stat().st_size
    digests = _hashes(target)
    report: Dict[str, Any] = {"dataset": RAVDESS["dataset_id"], "bytes": size, "sha256": digests["sha256"],
                              "size_ok": size == RAVDESS["bytes"], "md5_ok": digests["md5"] == RAVDESS["md5"]}
    if not (report["size_ok"] and report["md5_ok"]):
        report["result"] = "integrity_failed"
        return report
    inspection = archive_safety.inspect_zip(target)
    report["archive_safe"] = bool(inspection.get("safe"))
    if not report["archive_safe"]:
        report["result"] = "archive_unsafe"
        report["findings"] = inspection.get("findings", [])
        return report
    if not paths["extracted"].exists():
        archive_safety.safe_extract(target, paths["extracted"])
    wavs = sorted(paths["extracted"].rglob("*.wav"))
    report["wav_files"] = len(wavs)
    report["wav_count_ok"] = len(wavs) == RAVDESS["expected_wav"]
    report["result"] = "verified" if report["wav_count_ok"] else "unexpected_member_count"
    return report


def _read_pointer(path: Path) -> Optional[Dict[str, Any]]:
    """Parse a Git LFS pointer file; None if the file is not a pointer."""
    if path.stat().st_size > 1024:
        return None
    text = path.read_bytes().decode("ascii", errors="replace")
    if not text.startswith("version https://git-lfs"):
        return None
    fields = dict(line.split(" ", 1) for line in text.splitlines() if " " in line)
    oid = fields.get("oid", "")
    if not oid.startswith("sha256:") or not fields.get("size", "").isdigit():
        return None
    return {"sha256": oid[len("sha256:"):], "bytes": int(fields["size"])}


def snapshot_crema_pointers(root: Path) -> Dict[str, Any]:
    """Record every AudioWAV pointer (name -> sha256, bytes) in a private manifest. No network."""
    src = governance.resolve_under(root, CREMA["pointer_dir"])
    entries: Dict[str, Dict[str, Any]] = {}
    not_pointer = 0
    for path in sorted(src.glob("*.wav")):
        ptr = _read_pointer(path)
        if ptr is None:
            not_pointer += 1
            continue
        entries[path.name] = ptr
    total = sum(e["bytes"] for e in entries.values())
    report: Dict[str, Any] = {"dataset": CREMA["dataset_id"], "pointers": len(entries), "not_pointer": not_pointer,
                              "bytes": total, "count_ok": len(entries) == CREMA["expected_wav"],
                              "bytes_ok": total == CREMA["expected_bytes"]}
    if not (report["count_ok"] and report["bytes_ok"] and not not_pointer):
        report["result"] = "unexpected_pointer_set"
        return report
    target = governance.resolve_under(root, CREMA["pointer_manifest"])
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"dataset": CREMA["dataset_id"], "files": entries}, indent=0, sort_keys=True)
    target.write_text(body, encoding="utf-8")
    report["manifest_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    report["result"] = "verified"
    return report


def verify_crema(root: Path, audio_dir: Optional[str] = None) -> Dict[str, Any]:
    """Check downloaded AudioWAV files against the pointer manifest (size and sha256)."""
    manifest_path = governance.resolve_under(root, CREMA["pointer_manifest"])
    if not manifest_path.is_file():
        return {"dataset": CREMA["dataset_id"], "result": "no_pointer_manifest",
                "hint": "run snapshot-crema-pointers first"}
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
    audio = governance.resolve_under(root, audio_dir or CREMA["audio_dir"])
    missing = still_pointer = size_mismatch = hash_mismatch = ok = 0
    total = 0
    for name, exp in expected.items():
        path = audio / name
        if not path.is_file():
            missing += 1
            continue
        size = path.stat().st_size
        if _read_pointer(path) is not None:
            still_pointer += 1
            continue
        if size != exp["bytes"]:
            size_mismatch += 1
            continue
        total += size
        if _hashes(path)["sha256"] == exp["sha256"]:
            ok += 1
        else:
            hash_mismatch += 1
    extra = sum(1 for p in audio.glob("*.wav") if p.name not in expected) if audio.is_dir() else 0
    report = {"dataset": CREMA["dataset_id"], "expected_files": len(expected), "verified": ok, "missing": missing,
              "still_pointer": still_pointer, "size_mismatch": size_mismatch, "hash_mismatch": hash_mismatch,
              "unexpected_extra_files": extra, "bytes": total}
    report["result"] = "verified" if (ok == len(expected) == CREMA["expected_wav"] and not extra) \
        else "incomplete_or_failed"
    return report


def status(root: Path) -> Dict[str, Any]:
    paths = ravdess_paths(root)
    audio = governance.resolve_under(root, CREMA["audio_dir"])
    wavs = list(audio.glob("*.wav")) if audio.is_dir() else []
    return {
        "ravdess_zip_present": paths["zip"].is_file(),
        "ravdess_extracted": paths["extracted"].is_dir(),
        "crema_pointer_manifest_present": governance.resolve_under(root, CREMA["pointer_manifest"]).is_file(),
        "crema_audio_dir_present": audio.is_dir(),
        "crema_wav_entries": len(wavs),
        "crema_still_lfs_pointers": sum(1 for p in wavs if _read_pointer(p) is not None),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.data.ser_audio", description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=None, help="defaults to SAHAY_DATASETS_ROOT")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("snapshot-crema-pointers")
    sub.add_parser("fetch-ravdess")
    v = sub.add_parser("verify-crema")
    v.add_argument("--audio-dir", default=None, help=f"relative to the root; default {CREMA['audio_dir']}")
    args = parser.parse_args(argv)
    root = governance.dataset_root(args.root)
    if args.cmd == "verify-crema":
        report = verify_crema(root, args.audio_dir)
    else:
        handler = {"status": status, "snapshot-crema-pointers": snapshot_crema_pointers,
                   "fetch-ravdess": fetch_ravdess}[args.cmd]
        report = handler(root)
    print(json.dumps(report, indent=1))
    return 0 if report.get("result", "verified") == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())
