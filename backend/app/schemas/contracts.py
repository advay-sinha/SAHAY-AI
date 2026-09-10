"""Pydantic request/response schemas mirroring docs/contracts/CONTRACTS.md.

The victim-facing schemas here are the second line of defence behind
app/ws/fanout.py: `extra="forbid"` means a widened payload fails validation
rather than reaching a victim client.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Lang = Literal["hi", "en"]
Band = Literal["Low", "Moderate", "High", "Critical"]
Decision = Literal["confirm", "modify", "reject"]


class VictimSafeModel(BaseModel):
    """Base for anything a victim client may receive. Rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


# --- Events a victim client MAY receive (CONTRACTS.md section 2) -------------


class AssistantTurn(VictimSafeModel):
    turn_id: str
    text: str
    lang: Lang
    intent: str
    audio: Literal["streaming", "prerecorded"]


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


class TimelineUpdate(VictimSafeModel):
    stage: str
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
    type: Literal["crisis", "threat", "medical", "coercion"]
    severity: str
    evidence_turn_ids: List[str] = Field(default_factory=list)
    requires_ack: bool = True


class ActionRecommended(BaseModel):
    """An AI recommendation. It has no decision field: a human decides."""

    action_id: str
    action_type: str
    rationale: str
    policy_citations: List[str] = Field(default_factory=list)
    confidence: float
    status: Literal["awaiting_decision", "decided"] = "awaiting_decision"


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
    """HANDOVER.md 12.4: `{token, role}`. display_name is additive."""

    model_config = ConfigDict(extra="forbid")

    token: str
    role: Literal["executive", "supervisor"]
    display_name: str


class CreateSessionRequest(BaseModel):
    channel: Literal["voice", "chat"] = "voice"
    consent: Literal["granted", "declined", "pending"] = "pending"
    lang: Lang = "hi"


class CreateSessionResponse(VictimSafeModel):
    session_id: str
    state: str
    consent: str
    lang: Lang
    ai_disclosure: str
    human_request_available: bool


class ChatMessage(BaseModel):
    type: Literal["chat.message"] = "chat.message"
    text: str
    lang: Lang = "hi"


class RequestHuman(BaseModel):
    type: Literal["request_human"] = "request_human"


class DecisionRequest(BaseModel):
    action_id: str
    decision: Decision
    rationale: str
    officer_id: str


class OverrideRequest(BaseModel):
    band: Band
    # Required by contract. A blank reason is refused server-side.
    reason: str = Field(min_length=1)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app_env: str
    llm_provider: str
    assessment_runner: str
    database: str
    fixed_scripts_ready: bool
    detail: Dict[str, Any] = Field(default_factory=dict)
