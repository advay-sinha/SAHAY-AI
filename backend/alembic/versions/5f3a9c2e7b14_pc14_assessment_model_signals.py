"""PC-14: advisory model signals on each assessment cycle

Revision ID: 5f3a9c2e7b14
Revises: 8c1e5a7d3f20
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5f3a9c2e7b14"
down_revision: Union[str, None] = "8c1e5a7d3f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable and additive: existing rows and cycles without a signal stay NULL.
    with op.batch_alter_table("assessments") as batch:
        batch.add_column(sa.Column("model_signals", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("assessments") as batch:
        batch.drop_column("model_signals")
