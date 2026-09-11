"""Focused Task 3 reliability and security regression tests.

All values are synthetic. Database tests use the existing isolated backend
fixture or a temporary SQLite database and never access development data.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.tests.test_contract_decisions import DecisionBase
from backend.tests.test_vertical_slice import HAVE_DEPS


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestAuditMetadataProtection(DecisionBase):
    def record(self, action, detail):
        from backend.app.core.db import session_factory
        from backend.app.services import audit

        async def write():
            async with session_factory()() as db:
                result = await audit.record(db, action, detail=detail)
                await db.commit()
                return result

        return self.client.portal.call(write)

    def assert_rejected_without_row(self, action, detail, sensitive_value):
        from backend.app.services import audit

        before = self.db("SELECT count(*) FROM audit_log WHERE action=?", action)
        error_type = getattr(audit, "UnsafeAuditDetail", RuntimeError)
        with self.assertRaises(error_type) as caught:
            self.record(action, detail)
        self.assertNotIn(sensitive_value, str(caught.exception))
        self.assertEqual(
            self.db("SELECT count(*) FROM audit_log WHERE action=?", action), before
        )

    def test_rejects_prohibited_top_level_key_before_persistence(self):
        value = "synthetic-sensitive-narrative-alpha"
        self.assert_rejected_without_row(
            "task3.audit.top_level", {"victim_text": value}, value
        )

    def test_rejects_mixed_case_and_separator_variants(self):
        value = "synthetic-credential-beta"
        self.assert_rejected_without_row(
            "task3.audit.mixed_case", {"Access-ToKeN": value}, value
        )

    def test_rejects_prohibited_key_in_nested_dictionary(self):
        value = "synthetic-sensitive-narrative-gamma"
        self.assert_rejected_without_row(
            "task3.audit.nested", {"context": {"Raw_Message": value}}, value
        )

    def test_rejects_prohibited_dictionary_inside_a_list(self):
        value = "synthetic-sensitive-narrative-delta"
        self.assert_rejected_without_row(
            "task3.audit.list", {"changes": [{"utterance": value}]}, value
        )

    def test_safe_structured_metadata_remains_supported(self):
        detail = {
            "alert_id": "synthetic-alert-id",
            "status": "acknowledged",
            "decision": "confirm",
            "count": 2,
            "observed_at": "2030-01-02T03:04:05+00:00",
            "nested": [{"code": "S1", "enabled": True}],
        }
        self.assertTrue(self.record("task3.audit.safe", detail))
        stored = self.db(
            "SELECT detail FROM audit_log WHERE action=?", "task3.audit.safe"
        )
        self.assertEqual(len(stored), 1)
        for marker in ("synthetic-alert-id", "acknowledged", "confirm", "S1"):
            self.assertIn(marker, stored[0][0])


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestSeedCommandSafety(unittest.TestCase):
    REPO = Path(__file__).resolve().parents[2]
    PYTHON = REPO / "backend" / ".venv" / "Scripts" / "python.exe"

    def test_rejects_unsafe_target_before_session_factory_or_directory_write(self):
        from backend.seed import seed

        settings = SimpleNamespace(
            DATABASE_URL=(
                "postgresql+asyncpg://synthetic-user:synthetic-password@"
                "synthetic-private-host/synthetic-db?access_token=synthetic-query-secret"
            ),
            ensure_runtime_dirs=Mock(),
        )
        no_session = Mock(side_effect=AssertionError("session factory must not run"))
        with (
            patch.object(seed, "get_settings", return_value=settings),
            patch.object(seed, "session_factory", no_session, create=True),
            patch.object(seed, "_open_session_factory", no_session, create=True),
        ):
            error_type = getattr(seed, "UnsafeSeedTarget", RuntimeError)
            with self.assertRaises(error_type):
                asyncio.run(seed.seed(False, "synthetic-local-password"))
        settings.ensure_runtime_dirs.assert_not_called()
        no_session.assert_not_called()

    def test_remote_rejection_output_is_sanitized(self):
        markers = {
            "password": "synthetic-password-marker",
            "host": "synthetic-private-host-marker",
            "query": "synthetic-secret-query-marker",
        }
        env = dict(os.environ)
        env["DATABASE_URL"] = (
            "postgresql+asyncpg://synthetic-user:"
            f"{markers['password']}@{markers['host']}/synthetic-db"
            f"?access_token={markers['query']}"
        )
        env["SEED_PASSWORD"] = "synthetic-seed-password-marker"
        result = subprocess.run(
            [str(self.PYTHON), "-m", "backend.seed.seed"],
            cwd=str(self.REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 2, output)
        self.assertIn("seed refused", output.lower())
        for marker in (*markers.values(), env["SEED_PASSWORD"], env["DATABASE_URL"]):
            self.assertNotIn(marker, output)

    def test_disposable_sqlite_target_preserves_normal_seed_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "task3-seed.db"
            env = dict(os.environ)
            env["DATABASE_URL"] = (
                "sqlite+aiosqlite:///" + database.as_posix()
            )
            env["SEED_PASSWORD"] = "synthetic-local-seed-password"
            migrate = subprocess.run(
                [str(self.PYTHON), "-m", "alembic", "upgrade", "head"],
                cwd=str(self.REPO / "backend"),
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(migrate.returncode, 0, migrate.stderr[-2000:])
            result = subprocess.run(
                [str(self.PYTHON), "-m", "backend.seed.seed", "--reset"],
                cwd=str(self.REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertNotIn(env["SEED_PASSWORD"], output)
            self.assertIn("local", output.lower())
            connection = sqlite3.connect(database)
            try:
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM users").fetchone(), (3,)
                )
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM policy_chunks").fetchone(),
                    (6,),
                )
            finally:
                connection.close()


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestConcurrentAcknowledgement(DecisionBase):
    def test_competing_acknowledgements_have_one_authoritative_winner(self):
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.sql.dml import Update

        session = self.ready_case()
        case_id = session["case_id"]
        alert = self.packet(case_id)["alerts"][0]
        url = f"/cases/{case_id}/alerts/{alert['id']}/ack"
        headers = (self.login("exec1"), self.login("exec2"))

        original_execute = AsyncSession.execute
        update_gate = {"arrivals": 0, "event": None}

        async def execute_at_barrier(db, statement, *args, **kwargs):
            if isinstance(statement, Update) and statement.table.name == "alerts":
                if update_gate["event"] is None:
                    update_gate["event"] = asyncio.Event()
                update_gate["arrivals"] += 1
                if update_gate["arrivals"] == 2:
                    update_gate["event"].set()
                await asyncio.wait_for(update_gate["event"].wait(), timeout=5)
            return await original_execute(db, statement, *args, **kwargs)

        request_gate = threading.Barrier(3)

        def acknowledge(headers_for_request):
            request_gate.wait(timeout=5)
            return self.client.post(url, headers=headers_for_request)

        with patch.object(AsyncSession, "execute", new=execute_at_barrier):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(acknowledge, value) for value in headers]
                request_gate.wait(timeout=5)
                responses = [future.result(timeout=20) for future in futures]

        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertIn(responses[0].json()["acknowledged_by"], {"u-exec1", "u-exec2"})
        self.assertEqual(
            self.db(
                "SELECT count(*) FROM alerts WHERE id=? AND acknowledged_at IS NOT NULL",
                alert["id"],
            ),
            [(1,)],
        )
        self.assertEqual(
            self.db(
                "SELECT count(*) FROM audit_log WHERE action='alert.acknowledged' "
                "AND json_extract(detail, '$.alert_id')=?",
                alert["id"],
            ),
            [(1,)],
        )


if __name__ == "__main__":
    unittest.main()
