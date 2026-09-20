"""SQLAlchemy tables.

CONTRACTS.md section 6 fixes the table list: 15 tables since PC-03 restored the
dedicated `overrides` and `timeline_events` tables of HANDOVER.md section 11. `decisions_ai` and `decisions_human`
are separate tables and must stay that way: the record must never read as though
a machine decided.

`policy_chunks` is listed in the contract with pgvector. pgvector is EXT-110,
PROPOSED and deferred, so the local column stores the chunk text and a keyword
index instead. The table name and purpose are unchanged, so the later migration
is additive.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(128), default="")


class Session(TimestampMixin, Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Frozen enum (PC-10): mobile_voice | mobile_chat | portal_chat | upload
    channel: Mapped[str] = mapped_column(String(16), default="mobile_chat")
    lang: Mapped[str] = mapped_column(String(8), default="hi")
    state: Mapped[str] = mapped_column(String(4), default="S0")
    human_joined: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set when an officer takes over. Officer messages (PC-07) require it.
    human_joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Consent(TimestampMixin, Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))  # granted | declined | pending
    disclosure_version: Mapped[str] = mapped_column(String(32), default="v1")


class Turn(TimestampMixin, Base):
    __tablename__ = "turns"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_turns_session_seq"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(16))  # victim | assistant | officer (PC-07; HANDOVER.md section 11)
    text: Mapped[str] = mapped_column(Text, default="")
    lang: Mapped[str] = mapped_column(String(8), default="hi")
    state: Mapped[str] = mapped_column(String(4), default="")
    intent: Mapped[str] = mapped_column(String(48), default="")
    # Recorded so the console can audit what the assistant said and why.
    was_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    guardrail_reason: Mapped[str] = mapped_column(String(120), default="")
    asr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lang_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Assistant turns: "draft" (unreviewed fallback text) or "" for victim turns.
    review_status: Mapped[str] = mapped_column(String(24), default="")


class Case(TimestampMixin, Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    band: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    claimed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    taken_over_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    structured: Mapped[dict] = mapped_column(JSON, default=dict)
    # open -> claimed -> taken_over -> closed. Transitions enforced in services.
    status: Mapped[str] = mapped_column(String(24), default="open")
    svi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    needs_human: Mapped[bool] = mapped_column(Boolean, default=True)
    # "ai" when the band comes from an assessment, "override" after an officer
    # overrides it. The cause of every change is in assessments / audit_log.
    band_source: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    takeover_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Assessment(TimestampMixin, Base):
    __tablename__ = "assessments"
    __table_args__ = (UniqueConstraint("case_id", "cycle_index", name="uq_assessments_case_cycle"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    # Nullable because the engine abstains rather than fabricating a score.
    svi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    band: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    needs_human: Mapped[bool] = mapped_column(Boolean, default=True)
    aggregate_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    overrides_applied: Mapped[dict] = mapped_column(JSON, default=list)
    abstention_reasons: Mapped[dict] = mapped_column(JSON, default=list)
    cycle_index: Mapped[int] = mapped_column(Integer, default=0)
    trigger_turn_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    cause: Mapped[str] = mapped_column(String(160), default="")
    uncertainty: Mapped[dict] = mapped_column(JSON, default=dict)
    pipeline_version: Mapped[str] = mapped_column(String(48), default="")
    # PC-08: which dimensions were available, which were structurally
    # unavailable for the channel, and the weight denominator applied.
    scoring_version: Mapped[str] = mapped_column(String(32), default="")
    normalization: Mapped[dict] = mapped_column(JSON, default=dict)


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("case_id", "type", name="uq_alerts_case_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16))  # crisis | threat | medical | coercion
    severity: Mapped[str] = mapped_column(String(16))
    evidence_turn_ids: Mapped[dict] = mapped_column(JSON, default=list)
    requires_ack: Mapped[bool] = mapped_column(Boolean, default=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Recommendation(TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("case_id", "action_type", name="uq_recommendations_case_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(48))
    rationale: Mapped[str] = mapped_column(Text, default="")
    policy_citations: Mapped[dict] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    label: Mapped[str] = mapped_column(String(64), default="")
    evidence_turn_ids: Mapped[dict] = mapped_column(JSON, default=list)


class DecisionAI(TimestampMixin, Base):
    """What the system proposed. Never a decision in the human sense."""

    __tablename__ = "decisions_ai"
    __table_args__ = (UniqueConstraint("recommendation_id", name="uq_decisions_ai_recommendation"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"))
    proposed_action: Mapped[str] = mapped_column(String(48))
    model_version: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class DecisionHuman(TimestampMixin, Base):
    """What a named officer decided. Separate table by contract."""

    __tablename__ = "decisions_human"
    __table_args__ = (UniqueConstraint("recommendation_id", name="uq_decisions_human_recommendation"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True
    )
    officer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(16))  # confirm | modify | reject
    rationale: Mapped[str] = mapped_column(Text, default="")


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_audit_log_dedupe_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[Optional[str]] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_kind: Mapped[str] = mapped_column(String(16))  # human | system
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    # Set for events that must happen at most once (a timeline stage, an
    # acknowledgement). NULLs are not unique-constrained, so ordinary events
    # are unaffected. The log stays append-only either way.
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)


class PolicyChunk(TimestampMixin, Base):
    """Retrieval corpus. Local keyword index; pgvector is EXT-110, deferred."""

    __tablename__ = "policy_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(128))
    citation: Mapped[str] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text)
    keywords: Mapped[dict] = mapped_column(JSON, default=list)


class LatencyMetric(TimestampMixin, Base):
    __tablename__ = "latency_metrics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    turn_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    stage: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[float] = mapped_column(Float)


class Override(TimestampMixin, Base):
    """A band override by a named officer. HANDOVER.md section 11; PC-03.

    `reason` is NOT NULL here and also enforced at the endpoint (400).
    """

    __tablename__ = "overrides"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    officer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    from_band: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    to_band: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class TimelineEvent(TimestampMixin, Base):
    """A victim-safe timeline stage. HANDOVER.md section 11; PC-03.

    This table is the authoritative victim timeline. `dedupe_key` makes each
    stage happen once per case (per recommendation for action_taken).
    """

    __tablename__ = "timeline_events"
    __table_args__ = (UniqueConstraint("case_id", "dedupe_key", name="uq_timeline_events_case_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(160))
    dedupe_key: Mapped[str] = mapped_column(String(160))
