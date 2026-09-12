"""PC-11 durable chat and human-request identifiers.

Revision ID: 9c7e2d4a11b0
Revises: 7fbad9360da7
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9c7e2d4a11b0"
down_revision: Union[str, None] = "7fbad9360da7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("turns", schema=None) as batch_op:
        batch_op.add_column(sa.Column("client_message_id", sa.String(length=18), nullable=True))
        batch_op.create_unique_constraint(
            "uq_turns_session_client_message", ["session_id", "client_message_id"]
        )

    op.create_table(
        "human_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=18), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "request_id", name="uq_human_requests_session_request"),
    )
    with op.batch_alter_table("human_requests", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_human_requests_session_id"), ["session_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("human_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_human_requests_session_id"))
    op.drop_table("human_requests")

    with op.batch_alter_table("turns", schema=None) as batch_op:
        batch_op.drop_constraint("uq_turns_session_client_message", type_="unique")
        batch_op.drop_column("client_message_id")
