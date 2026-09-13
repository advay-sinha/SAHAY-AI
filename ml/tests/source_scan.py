"""Shared traversal for the static source scans in this test suite.

Several firewall tests read every file under ``ml/`` and assert that no forbidden
import, dataset marker or private bypass appears. A local development environment
created at ``ml/.venv`` (docs/LOCAL_SETUP.md) puts third-party code under the same
tree, so a bare ``rglob`` reports pip's vendored modules as project source.

Only recognised environment and generated directories are skipped, and only when
they sit *below* the scanned root, so a checkout whose own path contains one of
these names is still scanned in full. No real ``ml`` package may use these names;
``test_source_scan`` proves every tracked ``ml/`` source file is still visited.
"""

from pathlib import Path
from typing import Iterator

#: Directory names that hold installed third-party code or interpreter caches.
EXCLUDED_DIR_NAMES = frozenset({".venv", "site-packages", "__pycache__"})

ML = Path(__file__).resolve().parents[1]


def is_excluded(path: Path, root: Path) -> bool:
    """True when `path` lies inside an excluded directory below `root`."""
    parents = path.relative_to(root).parts[:-1]
    return any(part in EXCLUDED_DIR_NAMES for part in parents)


def iter_source_files(root: Path = ML, pattern: str = "*.py") -> Iterator[Path]:
    """Yield files under `root` matching `pattern`, in sorted order, skipping
    environment and generated directories."""
    for path in sorted(root.rglob(pattern)):
        if path.is_file() and not is_excluded(path, root):
            yield path
