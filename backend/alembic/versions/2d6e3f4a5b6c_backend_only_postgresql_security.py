"""backend-only PostgreSQL security posture

Revision ID: 2d6e3f4a5b6c
Revises: 7fbad9360da7
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2d6e3f4a5b6c"
down_revision: Union[str, None] = "7fbad9360da7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "public"
APPLICATION_TABLES = (
    "users",
    "sessions",
    "consents",
    "turns",
    "cases",
    "assessments",
    "alerts",
    "recommendations",
    "decisions_ai",
    "decisions_human",
    "overrides",
    "timeline_events",
    "audit_log",
    "policy_chunks",
    "latency_metrics",
)
CLIENT_ROLES = ("anon", "authenticated")


def _qualified(bind, schema: str, name: str) -> str:
    quote = bind.dialect.identifier_preparer.quote
    return f"{quote(schema)}.{quote(name)}"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table_name in APPLICATION_TABLES:
        table = _qualified(bind, SCHEMA, table_name)
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM PUBLIC"))
        for role in CLIENT_ROLES:
            quoted_role = bind.dialect.identifier_preparer.quote(role)
            op.execute(
                sa.text(
                    "DO $sahay$ BEGIN "
                    f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
                    f"EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE {table} FROM {quoted_role}'; "
                    "END IF; END $sahay$"
                )
            )

    table_names = ", ".join(f"'{name}'" for name in APPLICATION_TABLES)
    op.execute(
        sa.text(
            "DO $sahay$ DECLARE item record; BEGIN "
            "FOR item IN SELECT DISTINCT seq_ns.nspname AS schema_name, "
            "seq.relname AS sequence_name FROM pg_class AS seq "
            "JOIN pg_namespace AS seq_ns ON seq_ns.oid = seq.relnamespace "
            "JOIN pg_depend AS dependency ON dependency.objid = seq.oid "
            "JOIN pg_class AS app_table ON app_table.oid = dependency.refobjid "
            "JOIN pg_namespace AS table_ns ON table_ns.oid = app_table.relnamespace "
            f"WHERE seq.relkind = 'S' AND table_ns.nspname = '{SCHEMA}' "
            f"AND app_table.relname IN ({table_names}) LOOP "
            "EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %I.%I FROM PUBLIC', "
            "item.schema_name, item.sequence_name); "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            "EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %I.%I FROM anon', "
            "item.schema_name, item.sequence_name); END IF; "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN "
            "EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %I.%I FROM authenticated', "
            "item.schema_name, item.sequence_name); END IF; "
            "END LOOP; END $sahay$"
        )
    )


def downgrade() -> None:
    # Deliberately do not restore broad client grants or disable RLS. A rollback
    # must not silently turn backend-only victim/case tables into public tables.
    pass
