"""Pydantic request/response schemas mirroring docs/contracts/CONTRACTS.md.

The victim-facing schemas here are the second line of defence behind
app/ws/fanout.py: `extra="forbid"` means a widened payload fails validation
rather than reaching a victim client.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.enums import (
    ALERT_SEVERITIES,
    ALERT_TYPES,
    BANDS,
    CONSENT_STATUSES,
    DECISIONS,
    SESSION_CHANNELS,
    TIMELINE_STAGES,
)

# Literal types are built from the frozen enums in core/enums.py (CONTRACTS.md
# section 9), so there is one list per enum, not a second copy here.
Lang = Literal["hi", "en"]
Band = Literal[BANDS]
Decision = Literal[DECISIONS]
Channel = Literal[SESSION_CHANNELS]
ConsentStatus = Literal[CONSENT_STATUSES]
AlertType = Literal[ALERT_TYPES]
AlertSeverity = Literal[ALERT_SEVERITIES]
TimelineStage = Literal[TIMELINE_STAGES]
#: PC-12. "none" is a text-only turn that claims no audio; the field stays required.
ASSISTANT_AUDIO = ("none", "streaming", "prerecorded")
AssistantAudio = Literal[ASSISTANT_AUDIO]


class VictimSafeModel(BaseModel):
    """Base for anything a victim client may receive. Rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


# --- Events a victim client MAY receive (CONTRACTS.md section 2) -------------


class AssistantTurn(VictimSafeModel):
    turn_id: str
    text: str
    lang: Lang
    intent: str
    audio: AssistantAudio


class TranscriptLine(VictimSafeModel):
    turn_id: str
    speaker: Literal["victim", "assistant"]
    text: str
    lang: Lang
    ts: str


class SessionStatus(VictimSafeModel):
    state: str
    consent: str
    lang: Lang
    human_joined: bool


class OfficerMessage(VictimSafeModel):
    """PC-07: written by the human officer who took over. No assessment field.

    `origin` is always "human_officer" so the victim app can show plainly that
    a person, not the assistant, is speaking."""

    turn_id: str
    text: str
    lang: Lang
    ts: str
    origin: Literal["human_officer"]


class TimelineUpdate(VictimSafeModel):
    stage: TimelineStage
    label: str
    ts: str


class VictimTimeline(VictimSafeModel):
    """GET /cases/{id}/timeline — must contain no assessment field."""

    reference: str
    timeline: List[TimelineUpdate]


# --- Executive-console-only events (CONTRACTS.md section 3) -----------------


class DimensionValue(BaseModel):
    score: float
    conf: float
    evidence_turn_ids: List[str] = Field(default_factory=list)


class DimensionUpdate(BaseModel):
    dims: Dict[str, DimensionValue]
    svi: Optional[float] = None
    band: Optional[Band] = None
    needs_human: bool
    overrides_applied: List[str] = Field(default_factory=list)


class SafetyAlert(BaseModel):
    """alert.safety payload (PC-02). The alert's kind is `alert_type`; the
    envelope's `type` is always the event name and is never overwritten."""

    alert_type: AlertType
    severity: AlertSeverity
    evidence_turn_ids: List[str] = Field(default_factory=list)
    requires_ack: bool = True


class ActionRecommended(BaseModel):
    """An AI recommendation. It has no decision field: a human decides."""

    action_id: str
    action_type: str
    rationale: str
    policy_citations: List[str] = Field(default_factory=list)
    confidence: float


class EscalationPacket(BaseModel):
    case_id: str
    band: Optional[Band] = None
    alerts: List[SafetyAlert] = Field(default_factory=list)
    summary: str = ""
    ready: bool = True


# --- REST bodies (CONTRACTS.md section 4) -----------------------------------


class LoginRequest(BaseModel):
    # Length caps bound the Argon2 work a single request can force.
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    """CONTRACTS.md section 4: exact `{token, role, display_name}`."""

    model_config = ConfigDict(extra="forbid")

    token: str
    role: Literal["executive", "supervisor"]
    display_name: str


class CreateSessionRequest(BaseModel):
    channel: Channel = "mobile_chat"
    consent: ConsentStatus = "pending"
    lang: Lang = "hi"


class CreateSessionResponse(VictimSafeModel):
    """POST /sessions response, FROZEN by PC-09 (lead decision 2026-09-11).

    session_token  the VICTIM credential. Scoped to this one session (role
                   victim, session_id claim). It never authorises a console
                   route or another session. It is not an executive token;
                   executive tokens come only from POST /auth/login.
    ws_url         path only, `/ws/session/{session_id}`. It carries NO token,
                   so it is safe to log. Connecting (PC-11): the approved
                   protocol sends `{"type":"auth","token":...}` as the first
                   frame within five seconds. Query components are rejected.
    """

    session_id: str
    case_id: str
    reference_no: str
    session_token: str
    ws_url: str
    lang: Lang
    consent: ConsentStatus
    ai_disclosure: str
    human_request_available: bool


class EndSessionResponse(VictimSafeModel):
    case_id: str
    reference_no: str


class SocketFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SocketAuth(SocketFrame):
    type: Literal["auth"]
    token: str = Field(min_length=1, max_length=4096)


class SocketAuthOk(SocketFrame):
    type: Literal["auth.ok"]
    session_id: str
    role: Literal["victim", "executive", "supervisor"]


class ChatMessage(SocketFrame):
    type: Literal["chat.message"]
    client_message_id: str = Field(pattern=r"^m:[1-9][0-9]{0,15}$")
    text: str
    lang: Lang

    @field_validator("text")
    @classmethod
    def canonical_text(cls, value: str) -> str:
        canonical = value.strip()
        if not 1 <= len(canonical) <= 2000:
            raise ValueError("text must contain 1 to 2000 characters after trimming")
        return canonical


class ChatAckAccepted(SocketFrame):
    type: Literal["chat.ack"]
    client_message_id: str
    status: Literal["accepted", "duplicate"]
    turn_id: str = Field(min_length=1, max_length=64)


class ChatAckRejected(SocketFrame):
    type: Literal["chat.ack"]
    client_message_id: str
    status: Literal["rejected"]
    error: Literal["session_ended", "not_permitted", "id_conflict"]


class RequestHuman(SocketFrame):
    type: Literal["request_human"]
    request_id: str = Field(pattern=r"^h:[1-9][0-9]{0,15}$")


class HumanRequestAck(SocketFrame):
    type: Literal["human_request.ack"]
    request_id: str
    status: Literal["accepted", "duplicate"]


class HumanRequestRejected(SocketFrame):
    type: Literal["human_request.ack"]
    request_id: str
    status: Literal["rejected"]
    error: Literal["session_ended", "not_permitted"]


class DecisionRequest(BaseModel):
    action_id: str
    decision: Decision
    # Required (non-blank) for modify and reject; enforced server-side with 400.
    rationale: Optional[str] = ""
    # Must equal the signed-in officer; the server never trusts it on its own.
    officer_id: Optional[str] = None


class AlertAckResponse(BaseModel):
    """POST /cases/{id}/alerts/{alert_id}/ack, FROZEN by PC-01. Idempotent:
    a repeat returns the first acknowledgement unchanged."""

    model_config = ConfigDict(extra="forbid")

    alert_id: str
    case_id: str
    acknowledged_by: str
    acknowledged_at: str


class OfficerMessageRequest(BaseModel):
    """POST /cases/{id}/messages (PC-07). Blank or over-long text is a 400
    from the service, not a generic 422."""

    text: str = ""
    lang: Optional[Lang] = None


class OfficerMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str
    case_id: str
    origin: Literal["human_officer"]
    ts: str


class OverrideRequest(BaseModel):
    band: Band
    # REQUIRED by contract. Optional here only so a missing or blank reason is
    # refused by the service with 400 (HANDOVER.md 12.4), not a generic 422.
    reason: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app_env: str
    llm_provider: str
    assessment_runner: str
    database: str
    fixed_scripts_ready: bool
    detail: Dict[str, Any] = Field(default_factory=dict)
