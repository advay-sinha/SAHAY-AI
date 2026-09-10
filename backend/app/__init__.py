"""SAHAY-AI backend application package.

Import bootstrap
----------------
The backend imports the pure modules from `ml/`, which sit at the repository
root, not inside `backend/`. Different entry points run from different working
directories:

    scripts/start-backend.ps1   cwd = backend/   (uvicorn app.main:app)
    alembic                     cwd = backend/   (prepend_sys_path = .)
    pytest                      cwd = repo root  (pythonpath = ..)
    backend/seed/seed.py        cwd = anywhere

Without this, `uvicorn app.main:app` from `backend/` raises
`ModuleNotFoundError: No module named 'ml'` the first time a request touches the
dialogue scripts — a failure that only shows up at runtime, on the one entry
point the demo actually uses.

Putting the repository root on `sys.path` here fixes every entry point at once.
The MVP is one machine with no packaging step (root CLAUDE.md section 1), so
this is the smallest mechanism that works; an installable package would be the
answer once packaging exists.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
