"""Regression tests for three runtime defects the unit suite originally missed.

1. `uvicorn app.main:app` run from backend/ (how scripts/start-backend.ps1
   launches it) raised `ModuleNotFoundError: No module named 'ml'` on the first
   request, because ml/ lives at the repository root.
2. `.env.example` declared APP_ENV=development and POLICY_RETRIEVER=local, which
   the Settings model rejected -- so a .env copied from the example broke startup.
3. A relative DATABASE_URL resolved against the working directory, so running
   from backend/ would have created a second backend/runtime/ tree.

These need the EXT-001 packages. Under the bare-interpreter Tier 1 run they skip
rather than fail, so Tier 1 stays meaningful on a machine with nothing installed.
"""

import importlib.util
import os
import pathlib
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"

HAVE_SETTINGS = importlib.util.find_spec("pydantic_settings") is not None

#: The app imports all of these. Checking fastapi alone is not enough: a machine
#: can carry a stray global fastapi without the rest of the EXT-001 set.
_APP_DEPS = ("fastapi", "pydantic_settings", "sqlalchemy", "aiosqlite", "jwt", "pwdlib", "httpx")
HAVE_APP_DEPS = all(importlib.util.find_spec(m) is not None for m in _APP_DEPS)


def parse_env_file(path: pathlib.Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


@unittest.skipUnless(HAVE_SETTINGS, "pydantic-settings not installed (Tier 1 run)")
class TestEnvExampleIsValid(unittest.TestCase):
    def test_every_value_in_env_example_validates(self):
        from backend.app.core.config import Settings

        values = parse_env_file(REPO_ROOT / ".env.example")
        # Blank secrets are allowed in the example; the model supplies a default.
        values = {k: v for k, v in values.items() if v != ""}
        settings = Settings(_env_file=None, **values)
        self.assertEqual(settings.APP_ENV, values["APP_ENV"])
        self.assertEqual(settings.POLICY_RETRIEVER, values["POLICY_RETRIEVER"])
        self.assertEqual(settings.ASSESSMENT_RUNNER, values["ASSESSMENT_RUNNER"])
        self.assertEqual(settings.LLM_PROVIDER, "mock")

    def test_env_example_retriever_is_one_the_adapter_accepts(self):
        from backend.app.adapters.retrieval import get_retriever

        value = parse_env_file(REPO_ROOT / ".env.example")["POLICY_RETRIEVER"]
        self.assertIsNotNone(get_retriever(value))

    def test_env_example_commits_no_secret(self):
        values = parse_env_file(REPO_ROOT / ".env.example")
        for key in ("SECRET_KEY", "LLM_API_KEY"):
            self.assertEqual(values.get(key, ""), "", msg=f"{key} must be blank in .env.example")


@unittest.skipUnless(HAVE_SETTINGS, "pydantic-settings not installed (Tier 1 run)")
class TestPathsAnchorToRepoRoot(unittest.TestCase):
    def test_relative_sqlite_url_resolves_under_repo_runtime(self):
        from backend.app.core.config import Settings

        s = Settings(_env_file=None, DATABASE_URL="sqlite+aiosqlite:///./runtime/db/x.db")
        target = pathlib.Path(s.DATABASE_URL.split("///", 1)[1])
        self.assertEqual(target.resolve(), (REPO_ROOT / "runtime" / "db" / "x.db").resolve())
        self.assertNotIn(os.sep + "backend" + os.sep + "runtime", str(target.resolve()))

    def test_memory_and_non_sqlite_urls_are_left_alone(self):
        from backend.app.core.config import Settings

        mem = Settings(_env_file=None, DATABASE_URL="sqlite+aiosqlite:///:memory:")
        self.assertTrue(mem.DATABASE_URL.endswith(":memory:"))
        pg = Settings(_env_file=None, DATABASE_URL="postgresql+asyncpg://u:p@h/db")
        self.assertEqual(pg.DATABASE_URL, "postgresql+asyncpg://u:p@h/db")

    def test_relative_audio_path_resolves_under_repo_runtime(self):
        from backend.app.core.config import Settings

        s = Settings(_env_file=None, AUDIO_STORAGE_PATH="./runtime/audio")
        self.assertEqual(
            pathlib.Path(s.AUDIO_STORAGE_PATH).resolve(),
            (REPO_ROOT / "runtime" / "audio").resolve(),
        )


@unittest.skipUnless(HAVE_APP_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestAppImportsFromBackendCwd(unittest.TestCase):
    """Exactly how start-backend.ps1 and alembic run: cwd = backend/."""

    def test_app_main_imports_and_serves_health_from_backend_dir(self):
        code = (
            "from fastapi.testclient import TestClient\n"
            "from app.main import app\n"
            "r = TestClient(app).get('/health')\n"
            "assert r.status_code == 200, r.status_code\n"
            "assert r.json()['fixed_scripts_ready'] is False\n"
            "print('ok')\n"
        )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)  # prove it works without help from the caller
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(BACKEND),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr[-2000:])
        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
