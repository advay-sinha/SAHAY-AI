"""The private evaluation root, its layout and path confinement. Stdlib only.

The official corpus must never enter Git, so no executable path here is
hard-coded. Every command resolves its root from ``--root`` or the
``SAHAY_EVAL_ROOT`` environment variable and refuses to read or write outside
it. A machine-specific example lives in ``ml/eval/BLIND_EVALUATION.md`` and
nowhere in executable code: a path written into a module is the first step
to a path that gets used, and ``ml/tests/test_dataset_governance.py`` fails
the build if one appears here.

Layout, created by ``blind_corpus init`` and versioned by corpus version:

    <root>/
      intake/                    blank templates: submission, roster, review
      author-submissions/<v>/    one JSON per submission (contains narrative)
      assignments/<v>/           roster.json, assignments.json
      blinded-reviews/<v>/
        packets/                 exported blinded packets (contain narrative)
        records/                 imported review records, one file each
      adjudication/<v>/          adjudication records
      eligible/<v>/              eligibility report (ids and reasons only)
      frozen/<v>/                canonical corpus, labels, manifests
      manifests/<v>/             content-free freeze manifest (Git-safe copy)
      reports/<v>/               status and evaluation output
      rejected/<v>/              rejected and superseded records, kept forever
      ledgers/<v>/               submissions / reviews / adjudications / states .jsonl

``ledgers/`` is an addition to the recommended layout: the four append-only
hash chains are the integrity backbone and belong in one place that a backup
job can copy atomically.
"""

import os
import re
from pathlib import Path, PurePosixPath
from typing import Dict, List

#: The only configuration variable. No default, ever.
ROOT_ENV = "SAHAY_EVAL_ROOT"

#: Top-level directories created by `init`.
LAYOUT: tuple = (
    "intake",
    "author-submissions",
    "assignments",
    "blinded-reviews",
    "adjudication",
    "eligible",
    "frozen",
    "manifests",
    "reports",
    "rejected",
    "ledgers",
)

#: Corpus version: a short, filesystem-safe token such as "v1" or "v2-holdout".
VERSION_RE = re.compile(r"^v[0-9]+(?:-[a-z0-9]+)*$")

_LEDGERS = ("submissions", "reviews", "adjudications", "states")


class RootError(Exception):
    """The configured root is missing, unusable, or a path escaped it."""


def eval_root(explicit: str = "") -> Path:
    """Resolve the private root. A clear message that names no path contents."""
    value = explicit or os.environ.get(ROOT_ENV, "")
    if not str(value).strip():
        raise RootError(f"{ROOT_ENV} is not set and no --root was given; the private evaluation root has no default")
    root = Path(str(value)).expanduser()
    if not root.is_dir():
        raise RootError("the configured evaluation root does not exist or is not a directory")
    return root.resolve()


def check_version(version: str) -> str:
    if not VERSION_RE.match(str(version or "")):
        raise RootError("corpus version must look like v1 or v2-holdout")
    return str(version)


def safe_relative(rel: str) -> bool:
    """True for a relative path that cannot escape a root on any platform."""
    text = str(rel)
    if not text or text.startswith(("/", "\\")) or ":" in text:
        return False
    p = PurePosixPath(text.replace("\\", "/"))
    return not p.is_absolute() and ".." not in p.parts


def resolve_under(root: Path, rel: str) -> Path:
    """Resolve ``rel`` inside ``root``; refuse anything that escapes it.

    Both the syntactic check and the resolved-prefix check run, so a symlink
    or a ``..`` segment is caught even when the path does not exist yet.
    """
    if not safe_relative(rel):
        raise RootError("unsafe relative path (absolute, drive-qualified or parent-traversing)")
    root = Path(root).resolve()
    target = (root / str(rel).replace("\\", "/")).resolve()
    if target != root and root not in target.parents:
        raise RootError("path escapes the private evaluation root")
    return target


def version_dirs(version: str) -> Dict[str, str]:
    """Relative directory for each stage of one corpus version."""
    v = check_version(version)
    return {
        "submissions": f"author-submissions/{v}",
        "assignments": f"assignments/{v}",
        "packets": f"blinded-reviews/{v}/packets",
        "records": f"blinded-reviews/{v}/records",
        "adjudication": f"adjudication/{v}",
        "eligible": f"eligible/{v}",
        "frozen": f"frozen/{v}",
        "manifests": f"manifests/{v}",
        "reports": f"reports/{v}",
        "rejected": f"rejected/{v}",
        "ledgers": f"ledgers/{v}",
    }


def ledger_path(root: Path, version: str, name: str) -> Path:
    if name not in _LEDGERS:
        raise RootError(f"unknown ledger {name!r}")
    return resolve_under(root, f"{version_dirs(version)['ledgers']}/{name}.jsonl")


def init_root(root: Path, version: str) -> List[Path]:
    """Create the layout for one corpus version. Never writes corpus content."""
    root = Path(root).resolve()
    made: List[Path] = []
    for name in LAYOUT:
        d = resolve_under(root, name)
        d.mkdir(parents=True, exist_ok=True)
        made.append(d)
    for rel in version_dirs(version).values():
        d = resolve_under(root, rel)
        d.mkdir(parents=True, exist_ok=True)
        made.append(d)
    return made
