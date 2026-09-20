"""Backend tests always select an explicit disposable SQLite configuration."""

import os
from collections.abc import Mapping

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


def disposable_sqlite_subprocess_env(
    database_url: str, *, parent: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Build an isolated child environment for disposable Alembic tests."""
    if not database_url.startswith("sqlite+aiosqlite:///"):
        raise ValueError("test database must use disposable SQLite")

    env = dict(os.environ if parent is None else parent)
    env["APP_ENV"] = "test"
    env["DATABASE_URL"] = database_url
    # Process variables outrank the repository dotenv. Set this explicitly so
    # Alembic cannot select a developer's configured migration target.
    env["MIGRATION_DATABASE_URL"] = database_url
    return env
