"""Victim intake: sessions, consent, turns, human requests, session end.

The reply path, in order (root CLAUDE.md invariants 1 and 2):

  1. persist the victim turn
  2. synchronous crisis pre-check           -- before anything else decides
  3. deterministic dialogue policy          -- chooses one approved intent
  4. assistant text: a fallback for a question intent, or NOTHING when the
     intent is an unapproved fixed script (S0, S9, SX, SH fail closed)
  5. commit, publish victim-safe + executive events
  6. schedule the assessment cycle          -- background; never awaited here

Consent declined: turns are kept so a person can read them, but no AI analysis
ever runs, and the dialogue routes straight to a human (SH).

Crisis: SX, crisis alert (critical), takeover requested, band Critical when
scoring is permitted. Intake never resumes: SX is terminal in the policy.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ml.dialogue import next as dialogue_next
from ml.dialogue.states import State
from ml.guardrails import crisis_check
from ml.nlp.extraction import dialogue_slots, extract

from ..adapters.llm import get_provider
from ..core.config import get_settings
from ..core.enums import CONSENT_STATUSES, SESSION_CHANNELS
from ..core.errors import BadRequest, Conflict, NotFound
from ..models import Alert, Case, Consent, HumanRequest, Session, Turn
from . import audit
from .consent import CONSENT_DECLINED, CONSENT_GRANTED, CONSENT_PENDING
from .turn_loop import FixedScriptUnavailable, plan_turn

AI_DISCLOSURE = (
    "You are speaking with an AI assistant. A human officer reviews everything "
    "you say. You can ask to speak to a person at any time."
)

MAX_TURN_CHARS = 2000


@dataclass
class Outbound:
    """Events to publish after the transaction commits."""

    events: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)
    schedule_assessment: bool = False
    persisted_id: Optional[str] = None
    idempotency_status: str = "accepted"

    def add(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.events.append((event_type, payload))


def reference_for(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode()).hexdigest()[:6].upper()
    return f"SAH-{digest}"


def _iso(dt) -> str:
    return dt.isoformat() if dt else ""


async def get_session_row(db: AsyncSession, session_id: str) -> Session:
    row = await db.get(Session, session_id)
    if row is None:
        raise NotFound("session not found")
    return row


async def case_for_session(db: AsyncSession, session_id: str) -> Case:
    case = (await db.execute(select(Case).where(Case.session_id == session_id))).scalar_one_or_none()
    if case is None:
        raise NotFound("case not found")
    return case


async def consent_for(db: AsyncSession, session_id: str) -> str:
    row = (
        await db.execute(
            select(Consent).where(Consent.session_id == session_id).order_by(Consent.created_at.desc())
        )
    ).scalars().first()
    return row.status if row else CONSENT_PENDING


def status_payload(session: Session, consent: str) -> Dict[str, Any]:
    """session.status — victim-safe by construction (CONTRACTS.md section 2)."""
    return {
        "state": session.state,
        "consent": consent,
        "lang": session.lang,
        "human_joined": bool(session.human_joined),
    }


def transcript_payload(turn: Turn) -> Dict[str, Any]:
    return {
        "turn_id": turn.id,
        "speaker": "victim" if turn.speaker == "victim" else "assistant",
        "text": turn.text,
        "lang": turn.lang,
        "ts": _iso(turn.created_at),
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


async def create_session(
    db: AsyncSession,
    channel: str,
    consent: str,
    lang: str,
    session_id: Optional[str] = None,
) -> Tuple[Session, Case, Outbound]:
    """Create a session, its consent record and its case. Idempotent when an
    explicit session_id is supplied (the scenario runner does)."""
    out = Outbound()
    if channel not in SESSION_CHANNELS:
        raise BadRequest("unknown channel")
    if consent not in CONSENT_STATUSES:
        raise BadRequest("unknown consent status")
    if session_id:
        existing = await db.get(Session, session_id)
        if existing is not None:
            return existing, await case_for_session(db, session_id), out

    sid = session_id or str(uuid4())
    now = audit.now()
    session = Session(id=sid, channel=channel, lang=lang, state=State.S0_OPENING.value,
                      human_joined=False, created_at=now)
    case = Case(id=str(uuid4()), session_id=sid, reference=reference_for(sid), structured={},
                status="open", needs_human=True, created_at=now, updated_at=now)
    # The models declare foreign keys but no ORM relationships, so the unit of
    # work cannot infer insert order: flush the parent before its children, or
    # SQLite (foreign_keys=ON) rejects the case row.
    db.add(session)
    await db.flush()
    db.add(case)
    db.add(Consent(id=str(uuid4()), session_id=sid, status=consent, disclosure_version="v1",
                   created_at=now))
    await db.flush()

    await audit.record(db, "session.created", case_id=case.id,
                       detail={"channel": channel, "lang": lang, "consent": consent})
    await audit.record(db, f"consent.{consent}", case_id=case.id)
    await audit.timeline(db, case.id, "request_received")

    # S0 is a fixed script. It is not approved, so it is NOT spoken: fail
    # closed, record why, and move to listening. The AI disclosure is still
    # delivered — by the client from `ai_disclosure`, not by an unreviewed script.
    await audit.record(db, "fixed_script.unavailable", case_id=case.id, detail={"state": "S0"})
    if consent == CONSENT_DECLINED:
        session.state = State.SH_HUMAN_HANDOFF.value
        await audit.record(db, "routed_to_human", case_id=case.id, detail={"reason": "consent_declined"})
    else:
        session.state = State.S1_FREE_NARRATIVE.value

    out.add("session.status", status_payload(session, consent))
    return session, case, out


# ---------------------------------------------------------------------------
# Turns
# ---------------------------------------------------------------------------


async def _turns(db: AsyncSession, session_id: str) -> List[Turn]:
    return list((await db.execute(
        select(Turn).where(Turn.session_id == session_id).order_by(Turn.seq)
    )).scalars())


def _turn_dicts(turns: List[Turn]) -> List[Dict[str, Any]]:
    return [{"id": t.id, "speaker": t.speaker, "text": t.text, "state": t.state} for t in turns]


async def _upsert_crisis_alert(db: AsyncSession, case: Case, turn_id: str) -> bool:
    """Raise (or extend) the crisis alert. Returns True if newly raised."""
    alert = (await db.execute(
        select(Alert).where(Alert.case_id == case.id, Alert.type == "crisis")
    )).scalar_one_or_none()
    if alert is None:
        try:
            async with db.begin_nested():
                db.add(Alert(id=str(uuid4()), case_id=case.id, type="crisis", severity="critical",
                             evidence_turn_ids=[turn_id], requires_ack=True, created_at=audit.now()))
        except IntegrityError:
            return False
        return True
    if turn_id not in (alert.evidence_turn_ids or []):
        alert.evidence_turn_ids = list(alert.evidence_turn_ids or []) + [turn_id]
    return False


async def submit_turn(
    db: AsyncSession,
    session_id: str,
    text: str,
    lang: Optional[str] = None,
    victim_index: Optional[int] = None,
    client_message_id: Optional[str] = None,
) -> Outbound:
    """Handle one victim text turn. See the module docstring for the order."""
    out = Outbound()
    text = (text or "").strip()
    if not text:
        raise BadRequest("empty message")
    if len(text) > MAX_TURN_CHARS:
        raise BadRequest("message too long")

    session = await get_session_row(db, session_id)
    if session.ended_at is not None:
        raise Conflict("session has ended")
    case = await case_for_session(db, session_id)
    consent = await consent_for(db, session_id)
    lang = lang or session.lang
    if client_message_id is not None and lang != session.lang:
        raise Conflict("message language is not permitted")

    if client_message_id is not None:
        existing = (await db.execute(select(Turn).where(
            Turn.session_id == session_id,
            Turn.client_message_id == client_message_id,
        ))).scalar_one_or_none()
        if existing is not None:
            if existing.text != text or existing.lang != lang:
                raise Conflict("client message id conflict")
            out.persisted_id = existing.id
            out.idempotency_status = "duplicate"
            return out

    turns = await _turns(db, session_id)
    # Idempotent replay: `victim_index` is the 1-based position among the
    # victim's own turns. (Sequence numbers are not predictable: whether an
    # assistant turn follows depends on which scripts are approved.)
    if victim_index is not None:
        own = [t for t in turns if t.speaker == "victim"]
        if victim_index <= len(own):
            if own[victim_index - 1].text != text:
                raise Conflict("a different message already occupies this position")
            return out
        if victim_index != len(own) + 1:
            raise Conflict("turns must be submitted in order")
    next_seq = max((t.seq for t in turns), default=0) + 1

    # 1. persist the victim turn, in the state it was said in
    victim = Turn(id=str(uuid4()), session_id=session_id, seq=next_seq, speaker="victim",
                  client_message_id=client_message_id, text=text, lang=lang,
                  state=session.state, created_at=audit.now())
    try:
        async with db.begin_nested():
            db.add(victim)
            await db.flush()
    except IntegrityError:
        if client_message_id is not None:
            existing = (await db.execute(select(Turn).where(
                Turn.session_id == session_id,
                Turn.client_message_id == client_message_id,
            ))).scalar_one_or_none()
            if existing is not None and existing.text == text and existing.lang == lang:
                out.persisted_id = existing.id
                out.idempotency_status = "duplicate"
                return out
            if existing is not None:
                raise Conflict("client message id conflict") from None
        raise Conflict("duplicate sequence number") from None
    out.persisted_id = victim.id
    turns.append(victim)
    out.add("transcript.line", transcript_payload(victim))

    # Consent and a completed human takeover both mute every AI path. The
    # victim turn remains available to the officer under the existing
    # retention rules, but nothing below this boundary may inspect it.
    if consent != CONSENT_GRANTED or session.human_joined:
        case.updated_at = audit.now()
        out.add("session.status", status_payload(session, consent))
        return out

    # 2. synchronous crisis pre-check, before policy
    pre = crisis_check(text)

    victims = [t for t in _turn_dicts(turns) if t["speaker"] == "victim"]
    slots = dialogue_slots(victims, extract(victims))
    flags: Dict[str, Any] = {
        "lang": lang if lang in ("hi", "en") else "hi",
        "crisis": pre["crisis"],
        "consent": False if consent == CONSENT_DECLINED else None,
        "human_joined": bool(session.human_joined),
    }

    # 3-4. policy, then text only if it may be spoken
    assistant_text: Optional[str] = None
    intent = ""
    try:
        plan = plan_turn(session.state, slots, text, flags, get_provider(get_settings().LLM_PROVIDER))
        next_state = plan["next_state"]
        intent = plan["intent"]
        assistant_text = plan["text"]
    except FixedScriptUnavailable:
        decision = dialogue_next(session.state, slots, text, flags)
        next_state, intent = decision["next_state"], decision["intent"]
        await audit.record(db, "fixed_script.unavailable", case_id=case.id,
                           detail={"state": next_state, "turn_id": victim.id})

    session.state = next_state

    if assistant_text:
        reply = Turn(id=str(uuid4()), session_id=session_id, seq=next_seq + 1, speaker="assistant",
                     text=assistant_text, lang=flags["lang"], state=next_state, intent=intent,
                     was_fallback=True, review_status="draft", created_at=audit.now())
        db.add(reply)
        await db.flush()
        out.add("assistant.turn", {"turn_id": reply.id, "text": reply.text, "lang": reply.lang,
                                   "intent": intent, "audio": "prerecorded"})
        out.add("transcript.line", transcript_payload(reply))

    # Crisis: forced Critical, alert, takeover request. Never resumes intake.
    if pre["crisis"]:
        raised = await _upsert_crisis_alert(db, case, victim.id)
        if case.takeover_requested_at is None:
            case.takeover_requested_at = audit.now()
            await audit.record(db, "takeover.requested", case_id=case.id,
                               detail={"reason": "crisis_precheck", "turn_id": victim.id})
        if consent != CONSENT_DECLINED and case.band != "Critical":
            previous = case.band
            case.band, case.band_source, case.needs_human = "Critical", "ai", True
            await audit.record(db, "band.changed", case_id=case.id, detail={
                "from": previous, "to": "Critical", "cause": "override:crisis_interrupt_forces_critical",
                "trigger_turn_id": victim.id})
        if raised:
            await audit.record(db, "alert.raised", case_id=case.id,
                               detail={"type": "crisis", "severity": "critical", "turn_id": victim.id})
            out.add("alert.safety", {"alert_type": "crisis", "severity": "critical",
                                     "evidence_turn_ids": [victim.id], "requires_ack": True})

    case.updated_at = audit.now()
    out.add("session.status", status_payload(session, consent))
    out.schedule_assessment = consent == CONSENT_GRANTED
    return out


async def request_human(
    db: AsyncSession, session_id: str, request_id: Optional[str] = None,
) -> Outbound:
    """The victim asked for a person. Always honoured, from any state."""
    out = Outbound()
    session = await get_session_row(db, session_id)
    case = await case_for_session(db, session_id)
    consent = await consent_for(db, session_id)
    if session.ended_at is not None:
        raise Conflict("session has ended")
    if request_id is not None:
        existing = (await db.execute(select(HumanRequest).where(
            HumanRequest.session_id == session_id,
            HumanRequest.request_id == request_id,
        ))).scalar_one_or_none()
        if existing is not None:
            out.persisted_id = existing.id
            out.idempotency_status = "duplicate"
            return out
        row = HumanRequest(id=str(uuid4()), session_id=session_id, request_id=request_id,
                           requested_at=audit.now())
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            existing = (await db.execute(select(HumanRequest).where(
                HumanRequest.session_id == session_id,
                HumanRequest.request_id == request_id,
            ))).scalar_one_or_none()
            if existing is not None:
                out.persisted_id = existing.id
                out.idempotency_status = "duplicate"
                return out
            raise Conflict("duplicate human request") from None
        out.persisted_id = row.id
    if session.state != State.SX_CRISIS.value:
        session.state = State.SH_HUMAN_HANDOFF.value
    case.needs_human = True
    dedupe = f"human.requested:{session_id}:{request_id}" if request_id else f"human.requested:{case.id}"
    await audit.record(db, "human.requested", case_id=case.id, dedupe_key=dedupe,
                       detail={"request_id": request_id} if request_id else None)
    # SH is a fixed script and is not approved: nothing is spoken.
    await audit.record(db, "fixed_script.unavailable", case_id=case.id, detail={"state": "SH"})
    out.add("session.status", status_payload(session, consent))
    return out


async def end_session(db: AsyncSession, session_id: str) -> Tuple[Case, Outbound]:
    """End the session. Idempotent. S9 is not approved, so nothing is spoken."""
    out = Outbound()
    session = await get_session_row(db, session_id)
    case = await case_for_session(db, session_id)
    consent = await consent_for(db, session_id)
    if session.ended_at is None:
        session.ended_at = audit.now()
        await audit.record(db, "session.ended", case_id=case.id)
        await audit.record(db, "fixed_script.unavailable", case_id=case.id, detail={"state": "S9"})
    row = await audit.timeline(db, case.id, "under_review")
    if row is not None:
        out.add("timeline.update", audit.timeline_payload(row))
    out.add("session.status", status_payload(session, consent))
    return case, out


async def count_turns(db: AsyncSession, session_id: str) -> int:
    return int((await db.execute(select(func.count()).select_from(Turn).where(Turn.session_id == session_id))).scalar())
