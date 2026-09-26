"""PC-11: console-only audio measurements on voice turns

Revision ID: 8c1e5a7d3f20
Revises: 2d6e3f4a5b6c
Create Date: 2026-09-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8c1e5a7d3f20"
down_revision: Union[str, None] = "2d6e3f4a5b6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable and additive: typed turns and every existing row keep NULL.
    with op.batch_alter_table("turns") as batch:
        batch.add_column(sa.Column("asr_quality", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("turns") as batch:
        batch.drop_column("asr_quality")
