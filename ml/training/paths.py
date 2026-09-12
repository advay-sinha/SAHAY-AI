"""Private training root, confinement and atomic JSON writes. Standard library only."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Optional

TRAINING_ROOT_ENV = "SAHAY_TRAINING_ROOT"
ROOT_LABEL = "<SAHAY_TRAINING_ROOT>"
EXTERNAL_CORPUS = "corpora/external-ext119-v1"
FICTIONAL_CORPUS = "corpora/fictional-sahay-v1"


class TrainingRootError(Exception):
    """A root or confinement refusal. Messages never contain an absolute path."""


def inside_sahay_checkout(path: Path) -> bool:
    for parent in (path, *path.parents):
        if (parent / ".git").exists() and (parent / "ml" / "training" / "__init__.py").is_file():
            return True
    return False


def training_root(explicit: Optional[str] = None) -> Path:
    raw = explicit if explicit else os.environ.get(TRAINING_ROOT_ENV, "")
    if not raw.strip():
        raise TrainingRootError(f"{TRAINING_ROOT_ENV} is not set and no --training-root was given; it has no default")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise TrainingRootError(f"the directory named by {TRAINING_ROOT_ENV} does not exist")
    if inside_sahay_checkout(root):
        raise TrainingRootError(f"{TRAINING_ROOT_ENV} is inside a SAHAY checkout; private outputs stay outside Git")
    return root


def confined(root: Path, *parts: str) -> Path:
    for part in parts:
        if not part or Path(part).is_absolute() or part.startswith(("/", "\\")) or ":" in part:
            raise TrainingRootError("absolute or empty path component refused")
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise TrainingRootError("path escapes the training root") from None
    return target


def label(path: Path, root: Path) -> str:
    try:
        return ROOT_LABEL + "/" + path.resolve().relative_to(root).as_posix()
    except ValueError:
        return "<outside-training-root>"


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8",
                   newline="\n")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
