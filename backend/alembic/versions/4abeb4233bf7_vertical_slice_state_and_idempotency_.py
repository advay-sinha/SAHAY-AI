"""vertical slice state and idempotency keys

Adds case workflow state, per-cycle assessment causes, recommendation evidence,
the AI proposal payload, and unique keys that make replays and repeated
requests idempotent at the database level:

    turns            (session_id, seq)
    assessments      (case_id, cycle_index)
    alerts           (case_id, type)
    recommendations  (case_id, action_type)
    decisions_ai     (recommendation_id)
    decisions_human  (recommendation_id)
    audit_log        (dedupe_key)   -- NULL for ordinary events

Still the 13 tables of CONTRACTS.md section 6. Every added NOT NULL column has a
server default, so the upgrade is safe on a database that already holds rows.

Revision ID: 4abeb4233bf7
Revises: db1fbb96898f
Create Date: 2026-09-10 22:01:50.791532
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4abeb4233bf7'
down_revision: Union[str, None] = 'db1fbb96898f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('requires_ack', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.create_unique_constraint('uq_alerts_case_type', ['case_id', 'type'])

    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cycle_index', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('trigger_turn_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('cause', sa.String(length=160), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('uncertainty', sa.JSON(), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('pipeline_version', sa.String(length=48), nullable=False, server_default=''))
        batch_op.create_unique_constraint('uq_assessments_case_cycle', ['case_id', 'cycle_index'])

    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dedupe_key', sa.String(length=160), nullable=True))
        batch_op.create_unique_constraint('uq_audit_log_dedupe_key', ['dedupe_key'])

    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=24), nullable=False, server_default='open'))
        batch_op.add_column(sa.Column('svi', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('needs_human', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('band_source', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('takeover_requested_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))

    with op.batch_alter_table('decisions_ai', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payload', sa.JSON(), nullable=False, server_default='{}'))
        batch_op.create_unique_constraint('uq_decisions_ai_recommendation', ['recommendation_id'])

    with op.batch_alter_table('decisions_human', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_decisions_human_recommendation', ['recommendation_id'])

    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('label', sa.String(length=64), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('evidence_turn_ids', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.create_unique_constraint('uq_recommendations_case_type', ['case_id', 'action_type'])

    with op.batch_alter_table('turns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('review_status', sa.String(length=24), nullable=False, server_default=''))
        batch_op.create_unique_constraint('uq_turns_session_seq', ['session_id', 'seq'])



def downgrade() -> None:
    with op.batch_alter_table('turns', schema=None) as batch_op:
        batch_op.drop_constraint('uq_turns_session_seq', type_='unique')
        batch_op.drop_column('review_status')

    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.drop_constraint('uq_recommendations_case_type', type_='unique')
        batch_op.drop_column('evidence_turn_ids')
        batch_op.drop_column('label')

    with op.batch_alter_table('decisions_human', schema=None) as batch_op:
        batch_op.drop_constraint('uq_decisions_human_recommendation', type_='unique')

    with op.batch_alter_table('decisions_ai', schema=None) as batch_op:
        batch_op.drop_constraint('uq_decisions_ai_recommendation', type_='unique')
        batch_op.drop_column('payload')

    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.drop_column('updated_at')
        batch_op.drop_column('takeover_requested_at')
        batch_op.drop_column('claimed_at')
        batch_op.drop_column('band_source')
        batch_op.drop_column('needs_human')
        batch_op.drop_column('svi')
        batch_op.drop_column('status')

    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_constraint('uq_audit_log_dedupe_key', type_='unique')
        batch_op.drop_column('dedupe_key')

    with op.batch_alter_table('assessments', schema=None) as batch_op:
        batch_op.drop_constraint('uq_assessments_case_cycle', type_='unique')
        batch_op.drop_column('pipeline_version')
        batch_op.drop_column('uncertainty')
        batch_op.drop_column('cause')
        batch_op.drop_column('trigger_turn_id')
        batch_op.drop_column('cycle_index')

    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_constraint('uq_alerts_case_type', type_='unique')
        batch_op.drop_column('requires_ack')
