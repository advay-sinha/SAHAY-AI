"""Local file storage with safe path validation.

Everything lives under one root inside the git-ignored runtime/ directory.
Every path is resolved and checked to be inside that root, so a crafted id such
as "../../.env" or an absolute path cannot escape it.

The text-first slice stores no audio. This adapter exists so later audio work
has a vetted place to write, and it is exercised by tests now.
"""

import re
from pathlib import Path
from typing import Optional, Protocol

_SAFE_PART = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class UnsafePath(ValueError):
    pass


class Storage(Protocol):
    name: str

    def path_for(self, *parts: str) -> Path: ...


class LocalStorage:
    name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def path_for(self, *parts: str) -> Path:
        if not parts:
            raise UnsafePath("no path parts")
        for part in parts:
            if not _SAFE_PART.match(part) or part in (".", ".."):
                raise UnsafePath("path part contains disallowed characters")
        candidate = self.root.joinpath(*parts).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise UnsafePath("path escapes the storage root")
        return candidate

    def put(self, data: bytes, *parts: str) -> Path:
        target = self.path_for(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def delete(self, *parts: str) -> bool:
        target = self.path_for(*parts)
        if target.is_file():
            target.unlink()
            return True
        return False


class NullStorage:
    """Discards everything. Used when consent was not granted."""

    name = "null"

    def path_for(self, *parts: str) -> Optional[Path]:  # type: ignore[override]
        return None
