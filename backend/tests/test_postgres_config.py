"""Safe PostgreSQL configuration and remote-seed boundaries."""

import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateTable

from backend.app.core.config import (
    DatabaseConfigurationError,
    Settings,
    normalize_database_url,
)
from backend.app.core.db import Base, attach_sqlite_pragmas, engine_options
from backend.seed.seed import (
    UnsafeSeedTarget,
    remote_seed_state_is_safe,
    validate_seed_target,
)


class TestDatabaseUrlConfiguration(unittest.TestCase):
    def test_plain_postgresql_url_is_normalized_without_rebuilding_credentials(self):
        raw = "postgresql://role:p%40ss@database.example.invalid:5432/app"
        normalized = normalize_database_url(raw, app_env="development")
        parsed = make_url(normalized)
        self.assertEqual(parsed.drivername, "postgresql+asyncpg")
        self.assertEqual(parsed.password, "p@ss")
        self.assertEqual(parsed.query["ssl"], "require")

    def test_ssl_is_required_and_insecure_values_are_rejected_safely(self):
        marker = "synthetic-credential-marker"
        raw = f"postgresql://role:{marker}@database.example.invalid/app?sslmode=disable"
        with self.assertRaises(DatabaseConfigurationError) as caught:
            normalize_database_url(raw, app_env="development")
        self.assertEqual(str(caught.exception), "database configuration is invalid")
        self.assertNotIn(marker, str(caught.exception))

    def test_transaction_pooler_port_is_rejected(self):
        with self.assertRaises(DatabaseConfigurationError):
            normalize_database_url(
                "postgresql://role:synthetic@database.example.invalid:6543/app",
                app_env="development",
            )

    def test_sqlite_is_test_only(self):
        with self.assertRaises(DatabaseConfigurationError):
            normalize_database_url("sqlite+aiosqlite:///:memory:", app_env="development")
        self.assertEqual(
            normalize_database_url("sqlite:///:memory:", app_env="test"),
            "sqlite+aiosqlite:///:memory:",
        )

    def test_database_url_is_required_without_environment_or_env_file(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(Exception) as caught:
                Settings(_env_file=None)
        self.assertIn("DATABASE_URL", str(caught.exception))

    def test_migration_url_is_preferred_when_configured(self):
        settings = Settings(
            _env_file=None,
            DATABASE_URL="postgresql://runtime:synthetic@runtime.example.invalid/app",
            MIGRATION_DATABASE_URL=(
                "postgresql://migration:synthetic@migration.example.invalid/app"
            ),
        )
        parsed = make_url(settings.database_url(for_migration=True))
        self.assertEqual(parsed.username, "migration")
        self.assertEqual(parsed.drivername, "postgresql+asyncpg")


class TestEngineOptions(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            DATABASE_POOL_SIZE=5,
            DATABASE_MAX_OVERFLOW=2,
            DATABASE_POOL_TIMEOUT_SECONDS=10.0,
            DATABASE_CONNECT_TIMEOUT_SECONDS=11.0,
            DATABASE_COMMAND_TIMEOUT_SECONDS=31.0,
        )

    def test_postgresql_pool_is_modest_and_pre_ping_enabled(self):
        options = engine_options(
            self.settings,
            "postgresql+asyncpg://role:synthetic@database.example.invalid/app?ssl=require",
        )
        self.assertTrue(options["pool_pre_ping"])
        self.assertEqual(options["pool_size"], 5)
        self.assertEqual(options["max_overflow"], 2)
        self.assertEqual(options["connect_args"]["timeout"], 11.0)
        self.assertEqual(options["connect_args"]["command_timeout"], 31.0)

    def test_sqlite_gets_no_postgresql_pool_or_command_options(self):
        options = engine_options(self.settings, "sqlite+aiosqlite:///:memory:")
        self.assertNotIn("pool_size", options)
        self.assertNotIn("max_overflow", options)
        self.assertEqual(options["connect_args"], {"timeout": 11.0})

    def test_sqlite_pragmas_are_not_attached_to_postgresql(self):
        target = SimpleNamespace(url=make_url("postgresql+asyncpg://role:x@db.invalid/app"))
        with patch("backend.app.core.db.event.listens_for") as listens_for:
            attach_sqlite_pragmas(target)
        listens_for.assert_not_called()


class TestPostgresqlMetadata(unittest.TestCase):
    def test_every_application_table_compiles_for_postgresql(self):
        import backend.app.models  # noqa: F401

        compiled = {
            table.name: str(CreateTable(table).compile(dialect=postgresql.dialect()))
            for table in Base.metadata.sorted_tables
        }
        self.assertEqual(len(compiled), 15)
        self.assertTrue(all("CREATE TABLE" in statement for statement in compiled.values()))

    def test_security_migration_names_exactly_the_model_tables(self):
        import importlib.util

        path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "2d6e3f4a5b6c_backend_only_postgresql_security.py"
        )
        spec = importlib.util.spec_from_file_location("postgres_security_revision", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertEqual(set(module.APPLICATION_TABLES), set(Base.metadata.tables))
        self.assertEqual(module.CLIENT_ROLES, ("anon", "authenticated"))


class TestRemoteSeedBoundary(unittest.TestCase):
    PROJECT = "syntheticproject"
    DIRECT = (
        "postgresql+asyncpg://role:synthetic@"
        "db.syntheticproject.supabase.co:5432/app?ssl=require"
    )

    def approve(self, url=None, **overrides):
        arguments = {
            "app_env": "demo",
            "allow_remote": True,
            "project_ref": self.PROJECT,
            "confirmation": "AUTHORIZE_EMPTY_SAHAY_DEMO_SEED",
        }
        arguments.update(overrides)
        return validate_seed_target(url or self.DIRECT, **arguments)

    def test_arbitrary_postgresql_host_is_refused(self):
        with self.assertRaises(UnsafeSeedTarget):
            self.approve("postgresql+asyncpg://role:x@database.example.invalid/app")

    def test_production_environment_is_refused(self):
        with self.assertRaises(UnsafeSeedTarget):
            self.approve(app_env="production")

    def test_missing_opt_in_is_refused(self):
        with self.assertRaises(UnsafeSeedTarget):
            self.approve(allow_remote=False)

    def test_transaction_pooler_is_refused(self):
        with self.assertRaises(UnsafeSeedTarget):
            self.approve(self.DIRECT.replace(":5432/", ":6543/"))

    def test_malformed_url_and_credential_errors_are_sanitized(self):
        marker = "synthetic-secret-marker"
        with self.assertRaises(UnsafeSeedTarget) as caught:
            self.approve(f"not-a-url-{marker}")
        self.assertEqual(
            str(caught.exception),
            "seed refused: database target is not an approved development/demo database",
        )
        self.assertNotIn(marker, str(caught.exception))

    def test_nonempty_remote_target_is_refused(self):
        self.assertFalse(
            remote_seed_state_is_safe(
                [0, 1], user_total=0, known_users=0, policy_total=0, known_policies=0
            )
        )
        self.assertFalse(
            remote_seed_state_is_safe(
                [0, 0], user_total=1, known_users=0, policy_total=0, known_policies=0
            )
        )

    def test_approved_empty_target_and_success_label_are_sanitized(self):
        label = self.approve()
        self.assertTrue(
            remote_seed_state_is_safe(
                [0, 0], user_total=0, known_users=0, policy_total=0, known_policies=0
            )
        )
        self.assertEqual(label, "approved Supabase development/demo")
        self.assertNotIn(self.PROJECT, label)
        self.assertNotIn("supabase.co", label)


if __name__ == "__main__":
    unittest.main()
