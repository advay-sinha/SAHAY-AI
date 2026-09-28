"""Pre-recorded fixed-script audio registry (M13, EXT-103).

S0, S9, SX and SH are spoken only from **human-recorded** audio of their **approved** text. The
audio lives outside Git in an audio root (``runtime/audio/fixed/`` by default, or
``SAHAY_FIXED_AUDIO_ROOT``), described by ``manifest.json``:

    {"assets": {"SX:hi": {"file": "SX-hi.wav", "sha256": "...", "text_sha256": "...",
                          "status": "recorded" | "approved", "recorded_by": "...",
                          "reviewed_by": "...", "reviewed_on": "YYYY-MM-DD"}}}

An asset is servable only when all of these hold (``servable``):
- the fixed script itself is APPROVED (``ml.dialogue.scripts``);
- the recording is marked ``approved`` by a named reviewer who is not the person who recorded it;
- the recording was made from the currently approved text (``text_sha256``);
- the file on disk still matches its ``sha256``.

Anything else returns None and the client shows the text. Nothing here synthesises a fixed script.

    python -m ml.tts.presynth status
    python -m ml.tts.presynth register --key SX:hi --file rec.wav --recorded-by NAME
    python -m ml.tts.presynth approve  --key SX:hi --reviewed-by NAME
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..dialogue.scripts import record_for
from ..dialogue.states import State

KEYS = ("S0:hi", "S0:en", "S9:hi", "S9:en", "SX:hi", "SX:en", "SH:hi", "SH:en")
ROOT_ENV = "SAHAY_FIXED_AUDIO_ROOT"
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "runtime" / "audio" / "fixed"
MANIFEST = "manifest.json"
MAX_BYTES = 5 * 1024 * 1024


class AudioRegistryError(ValueError):
    """A refused registry change."""


def audio_root(explicit: Optional[str] = None) -> Path:
    return Path(explicit or os.environ.get(ROOT_ENV) or DEFAULT_ROOT)


def _state(key: str) -> State:
    code = key.split(":")[0]
    for s in State:
        if s.value == code:
            return s
    raise AudioRegistryError(f"unknown state in {key!r}")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_sha(text: str) -> str:
    return _sha_bytes(text.encode("utf-8"))


def approved_text(key: str) -> Optional[str]:
    """The approved fixed-script text for ``key``, or None when the script is not approved."""
    if key not in KEYS:
        raise AudioRegistryError(f"{key!r} is not a fixed-script key")
    lang = key.split(":")[1]
    rec = record_for(_state(key), lang)
    return rec.text if rec is not None and rec.speakable else None


def load_manifest(root: Path) -> Dict[str, Any]:
    path = root / MANIFEST
    if not path.is_file():
        return {"assets": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(root: Path, manifest: Mapping[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / (MANIFEST + ".partial")
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, root / MANIFEST)


def check(key: str, root: Path) -> Dict[str, Any]:
    """Every servability condition for one key, with the reason it fails."""
    entry = load_manifest(root).get("assets", {}).get(key)
    text = approved_text(key)
    reasons: List[str] = []
    if text is None:
        reasons.append("fixed script not approved")
    if entry is None:
        reasons.append("no recording registered")
    else:
        if entry.get("status") != "approved":
            reasons.append("recording not approved")
        if text is not None and entry.get("text_sha256") != text_sha(text):
            reasons.append("recording is of a different text version")
        path = root / str(entry.get("file", ""))
        if not path.is_file():
            reasons.append("audio file missing")
        elif _sha_bytes(path.read_bytes()) != entry.get("sha256"):
            reasons.append("audio file changed since registration")
    return {"key": key, "servable": not reasons, "reasons": reasons}


def servable(state: str, lang: str, root: Optional[Path] = None) -> Optional[Path]:
    """The approved recording's path, or None (the client then shows the text)."""
    key = f"{state}:{lang}"
    if key not in KEYS:
        return None
    root = root or audio_root()
    if not check(key, root)["servable"]:
        return None
    return root / load_manifest(root)["assets"][key]["file"]


def missing(root: Optional[Path] = None) -> Dict[str, List[str]]:
    """{key: reasons} for every fixed script that cannot be played yet."""
    root = root or audio_root()
    return {k: c["reasons"] for k in KEYS for c in [check(k, root)] if not c["servable"]}


def register(key: str, source: Path, recorded_by: str, root: Path) -> Dict[str, Any]:
    """Copy a human recording of the approved text into the audio root, status ``recorded``."""
    text = approved_text(key)
    if text is None:
        raise AudioRegistryError(f"{key}: the fixed script is not approved; record only approved text")
    if not recorded_by.strip():
        raise AudioRegistryError("recorded_by must name the person who recorded it")
    data = source.read_bytes()
    if not data or len(data) > MAX_BYTES or data[:4] != b"RIFF":
        raise AudioRegistryError("expected a WAV file under 5 MB")
    name = key.replace(":", "-") + ".wav"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(data)
    manifest = load_manifest(root)
    manifest.setdefault("assets", {})[key] = {
        "file": name, "sha256": _sha_bytes(data), "text_sha256": text_sha(text), "status": "recorded",
        "recorded_by": recorded_by.strip(), "recorded_on": time.strftime("%Y-%m-%d"),
        "reviewed_by": None, "reviewed_on": None}
    _save_manifest(root, manifest)
    return manifest["assets"][key]


def approve(key: str, reviewed_by: str, root: Path) -> Dict[str, Any]:
    """A named human reviewer, not the recorder, approves a registered recording."""
    manifest = load_manifest(root)
    entry = manifest.get("assets", {}).get(key)
    if entry is None:
        raise AudioRegistryError(f"{key}: no recording registered")
    reviewer = reviewed_by.strip()
    if not reviewer or reviewer.casefold() == str(entry.get("recorded_by", "")).casefold():
        raise AudioRegistryError("the reviewer must be named and must not be the person who recorded it")
    entry.update({"status": "approved", "reviewed_by": reviewer, "reviewed_on": time.strftime("%Y-%m-%d")})
    _save_manifest(root, manifest)
    return entry


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.tts.presynth", description=__doc__.split("\n")[0])
    parser.add_argument("--root", help=f"audio root (default {ROOT_ENV} or runtime/audio/fixed)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    r = sub.add_parser("register")
    r.add_argument("--key", required=True, choices=KEYS)
    r.add_argument("--file", required=True)
    r.add_argument("--recorded-by", required=True)
    a = sub.add_parser("approve")
    a.add_argument("--key", required=True, choices=KEYS)
    a.add_argument("--reviewed-by", required=True)
    args = parser.parse_args(argv)
    root = audio_root(args.root)
    try:
        if args.command == "register":
            out: Any = register(args.key, Path(args.file), args.recorded_by, root)
        elif args.command == "approve":
            out = approve(args.key, args.reviewed_by, root)
        else:
            out = {k: check(k, root) for k in KEYS}
    except AudioRegistryError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
