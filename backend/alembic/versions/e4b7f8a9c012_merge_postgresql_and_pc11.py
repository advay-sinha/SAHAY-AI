"""merge PostgreSQL security and controlled-MVP idempotency

Revision ID: e4b7f8a9c012
Revises: 2d6e3f4a5b6c, 9c7e2d4a11b0
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4b7f8a9c012"
down_revision: Union[str, Sequence[str], None] = (
    "2d6e3f4a5b6c",
    "9c7e2d4a11b0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "public"
APPLICATION_TABLES = ("human_requests",)
CLIENT_ROLES = ("anon", "authenticated")


def _qualified(bind, schema: str, name: str) -> str:
    quote = bind.dialect.identifier_preparer.quote
    return f"{quote(schema)}.{quote(name)}"


def upgrade() -> None:
    """Apply the backend-only posture to the table introduced by PC-11."""
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


def downgrade() -> None:
    # Preserve the restrictive PostgreSQL posture on rollback, matching the
    # published security migration's forward-only security boundary.
    pass
