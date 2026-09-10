"""Executable coverage for the released legacy-to-head Alembic migration."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class TestLegacyMigrationToHead(unittest.TestCase):
    REPO = Path(__file__).resolve().parents[2]
    BACKEND = REPO / "backend"
    PRE_HEAD = "4abeb4233bf7"
    HEAD = "7fbad9360da7"

    def alembic(self, env, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=str(self.BACKEND),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_released_migration_copies_only_eligible_legacy_audit_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "task3-legacy.db"
            env = dict(os.environ)
            env["DATABASE_URL"] = (
                "sqlite+aiosqlite:///" + database.as_posix()
            )

            pre_head = self.alembic(env, "upgrade", self.PRE_HEAD)
            self.assertEqual(pre_head.returncode, 0, pre_head.stderr[-2000:])

            created = "2030-01-02 03:04:05+00:00"
            audit_rows = (
                (
                    "audit-override",
                    "case-task3",
                    "user-task3",
                    "human",
                    "band.override",
                    json.dumps(
                        {
                            "from_band": "Moderate",
                            "to_band": "High",
                            "reason": "Synthetic officer review rationale.",
                        },
                        sort_keys=True,
                    ),
                    "legacy-override-task3",
                    created,
                ),
                (
                    "audit-support",
                    "case-task3",
                    "user-task3",
                    "human",
                    "timeline",
                    json.dumps({"stage": "support_arranged"}, sort_keys=True),
                    "timeline:case-task3:support:recommendation-task3",
                    created,
                ),
                (
                    "audit-retired",
                    "case-task3",
                    None,
                    "system",
                    "timeline",
                    json.dumps({"stage": "officer_speaking"}, sort_keys=True),
                    "timeline:case-task3:officer_speaking",
                    created,
                ),
                (
                    "audit-ineligible",
                    "case-task3",
                    "user-task3",
                    "human",
                    "band.override",
                    json.dumps(
                        {"from_band": "High", "to_band": "Critical", "reason": ""},
                        sort_keys=True,
                    ),
                    "legacy-ineligible-task3",
                    created,
                ),
            )
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "INSERT INTO users "
                    "(id, username, password_hash, role, display_name, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        "user-task3",
                        "synthetic-task3-officer",
                        "synthetic-password-hash",
                        "executive",
                        "Synthetic Task 3 Officer",
                        created,
                    ),
                )
                connection.execute(
                    "INSERT INTO sessions "
                    "(id, channel, lang, state, human_joined, ended_at, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("session-task3", "chat", "en", "S1", 0, None, created),
                )
                connection.execute(
                    "INSERT INTO cases "
                    "(id, session_id, reference, band, claimed_by, taken_over_at, "
                    "structured, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "case-task3",
                        "session-task3",
                        "SAH-TASK3",
                        "Moderate",
                        "user-task3",
                        None,
                        "{}",
                        created,
                    ),
                )
                connection.executemany(
                    "INSERT INTO audit_log "
                    "(id, case_id, actor_id, actor_kind, action, detail, dedupe_key, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    audit_rows,
                )
                connection.commit()
                original = connection.execute(
                    "SELECT id, case_id, actor_id, actor_kind, action, detail, "
                    "dedupe_key, created_at FROM audit_log ORDER BY id"
                ).fetchall()

            upgraded = self.alembic(env, "upgrade", "head")
            self.assertEqual(upgraded.returncode, 0, upgraded.stderr[-2000:])

            with closing(sqlite3.connect(database)) as connection:
                copied_override = connection.execute(
                    "SELECT case_id, officer_id, from_band, to_band, reason "
                    "FROM overrides"
                ).fetchall()
                self.assertEqual(
                    copied_override,
                    [
                        (
                            "case-task3",
                            "user-task3",
                            "Moderate",
                            "High",
                            "Synthetic officer review rationale.",
                        )
                    ],
                )
                copied_timeline = connection.execute(
                    "SELECT case_id, stage, dedupe_key FROM timeline_events"
                ).fetchall()
                self.assertEqual(
                    copied_timeline,
                    [
                        (
                            "case-task3",
                            "action_taken",
                            "action:recommendation-task3",
                        )
                    ],
                )
                after = connection.execute(
                    "SELECT id, case_id, actor_id, actor_kind, action, detail, "
                    "dedupe_key, created_at FROM audit_log ORDER BY id"
                ).fetchall()
                self.assertEqual(after, original)
                self.assertEqual(
                    connection.execute("SELECT version_num FROM alembic_version").fetchone(),
                    (self.HEAD,),
                )

            check = self.alembic(env, "check")
            self.assertEqual(check.returncode, 0, check.stderr[-2000:])
            self.assertIn("No new upgrade operations detected", check.stdout + check.stderr)


if __name__ == "__main__":
    unittest.main()
