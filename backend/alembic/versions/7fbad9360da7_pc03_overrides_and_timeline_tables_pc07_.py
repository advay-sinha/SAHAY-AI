"""PC-03 overrides and timeline tables; PC-07 / PC-08 / PC-10 columns and data

Revision ID: 7fbad9360da7
Revises: 4abeb4233bf7
Create Date: 2026-09-11

Lead decisions of 2026-09-11:

  PC-03  Restore the dedicated `overrides` and `timeline_events` tables
         (HANDOVER.md section 11). The audit log is an accountability record,
         not the authoritative timeline. Table count 13 -> 15.
  PC-07  sessions.human_joined_at, required before an officer may message.
  PC-08  assessments.scoring_version and assessments.normalization.
  PC-10  sessions.channel mapped onto the frozen enum
         (chat -> mobile_chat, voice -> mobile_voice).

Existing local data is preserved:
  * audit_log rows are append-only and are NOT modified or deleted;
  * `timeline` audit events are COPIED into timeline_events, mapped onto the
    frozen stage enum. Retired stages with no canonical equivalent
    (officer_speaking, recorded) stay in the audit log only;
  * `band.override` audit events are COPIED into overrides. Rows that cannot
    satisfy the new constraints (no officer, blank reason) are skipped and
    stay in the audit log.
"""

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7fbad9360da7"
down_revision: Union[str, None] = "4abeb4233bf7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Old stage -> frozen stage. None = no canonical equivalent; not copied.
STAGE_MAP = {
    "request_received": "request_received",
    "under_review": "under_review",
    "officer_assigned": "officer_assigned",
    "support_arranged": "action_taken",
    "officer_speaking": None,
    "recorded": None,
    "closed": "closed",
}
LABELS = {
    "request_received": "Your request has been received",
    "under_review": "Your request is being reviewed",
    "officer_assigned": "An officer has been assigned",
    "action_taken": "An officer has taken action on your request",
    "follow_up_scheduled": "A follow-up has been scheduled",
    "closed": "Your request has been closed",
}
CHANNEL_MAP = {"chat": "mobile_chat", "voice": "mobile_voice"}


def _detail(raw):
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}


def upgrade() -> None:
    op.create_table(
        "overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("officer_id", sa.String(length=36), nullable=False),
        sa.Column("from_band", sa.String(length=16), nullable=True),
        sa.Column("to_band", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["officer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("overrides", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_overrides_case_id"), ["case_id"], unique=False)

    op.create_table(
        "timeline_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "dedupe_key", name="uq_timeline_events_case_key"),
    )
    with op.batch_alter_table("timeline_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_timeline_events_case_id"), ["case_id"], unique=False)

    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("scoring_version", sa.String(length=32), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("normalization", sa.JSON(), nullable=False, server_default="{}"))

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("human_joined_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()

    # --- copy timeline audit events into timeline_events ------------------
    rows = bind.execute(sa.text(
        "SELECT case_id, detail, dedupe_key, created_at FROM audit_log "
        "WHERE action = 'timeline' AND case_id IS NOT NULL ORDER BY created_at")).fetchall()
    seen = set()
    for case_id, raw, key, created in rows:
        old = _detail(raw).get("stage")
        stage = STAGE_MAP.get(old)
        if stage is None:
            continue
        suffix = (key or "").split(":", 2)[-1] if key else stage
        dedupe = f"action:{suffix.split(':', 1)[1]}" if suffix.startswith("support:") else stage
        if (case_id, dedupe) in seen:
            continue
        seen.add((case_id, dedupe))
        bind.execute(sa.text(
            "INSERT INTO timeline_events (id, case_id, stage, label, dedupe_key, created_at) "
            "VALUES (:id, :case_id, :stage, :label, :dedupe, :created)"),
            {"id": str(uuid.uuid4()), "case_id": case_id, "stage": stage,
             "label": LABELS[stage], "dedupe": dedupe, "created": created})

    # --- copy band.override audit events into overrides --------------------
    rows = bind.execute(sa.text(
        "SELECT case_id, actor_id, detail, created_at FROM audit_log "
        "WHERE action = 'band.override' AND case_id IS NOT NULL ORDER BY created_at")).fetchall()
    for case_id, actor_id, raw, created in rows:
        d = _detail(raw)
        reason = (d.get("reason") or "").strip()
        if not actor_id or not reason or not d.get("to_band"):
            continue
        bind.execute(sa.text(
            "INSERT INTO overrides (id, case_id, officer_id, from_band, to_band, reason, created_at) "
            "VALUES (:id, :case_id, :officer, :from_band, :to_band, :reason, :created)"),
            {"id": str(uuid.uuid4()), "case_id": case_id, "officer": actor_id,
             "from_band": d.get("from_band"), "to_band": d["to_band"], "reason": reason,
             "created": created})

    # --- backfill human_joined_at from the case takeover time ---------------
    bind.execute(sa.text(
        "UPDATE sessions SET human_joined_at = "
        "(SELECT taken_over_at FROM cases WHERE cases.session_id = sessions.id) "
        "WHERE human_joined = 1 AND human_joined_at IS NULL"))

    # --- channel onto the frozen enum ---------------------------------------
    for old, new in CHANNEL_MAP.items():
        bind.execute(sa.text("UPDATE sessions SET channel = :new WHERE channel = :old"),
                     {"new": new, "old": old})


def downgrade() -> None:
    bind = op.get_bind()
    for old, new in CHANNEL_MAP.items():
        bind.execute(sa.text("UPDATE sessions SET channel = :old WHERE channel = :new"),
                     {"new": new, "old": old})

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_column("human_joined_at")

    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.drop_column("normalization")
        batch_op.drop_column("scoring_version")

    # The audit log still holds every copied event, so dropping the domain
    # tables loses nothing that existed before the upgrade.
    with op.batch_alter_table("timeline_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_timeline_events_case_id"))
    op.drop_table("timeline_events")
    with op.batch_alter_table("overrides", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_overrides_case_id"))
    op.drop_table("overrides")
