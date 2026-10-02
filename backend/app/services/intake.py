"""Victim intake: sessions, consent, turns, human requests, session end.

The reply path, in order (root CLAUDE.md invariants 1 and 2):

  1. persist the victim turn
  2. synchronous crisis pre-check           -- before anything else decides
  3. deterministic dialogue policy          -- chooses one approved intent
  4. assistant text: a fallback for a question intent, or NOTHING when the
     intent is an unapproved fixed script (S0, S9, SX, SH fail closed)
  5. commit, publish victim-safe + executive events
  6. schedule the assessment cycle          -- background; never awaited here

Consent declined: turns are kept so a person can read them, no AI analysis
ever runs, and the dialogue routes straight to a human (SH). Only the keyword
crisis pre-check still runs (lead decision 2026-10-02): on a match it alerts a
person and requests takeover, with no score.

Crisis: SX, crisis alert (critical), takeover requested, band Critical when
scoring is permitted. Intake never resumes: SX is terminal in the policy.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ml.dialogue import next as dialogue_next
from ml.dialogue.intents import STATE_INTENT
from ml.dialogue.scripts import text_for as fixed_script_text
from ml.dialogue.states import State
from ml.guardrails import crisis_check
from ml.nlp.extraction import dialogue_slots, extract

from ..adapters.llm import get_provider
from ..core.config import get_settings
from ..core.enums import CONSENT_STATUSES, SESSION_CHANNELS
from ..core.errors import BadRequest, Conflict, NotFound
from ..models import Alert, Case, Consent, Session, Turn
from . import audit, latency
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


def assistant_payload(turn: Turn) -> Dict[str, Any]:
    return {"turn_id": turn.id, "text": turn.text, "lang": turn.lang, "intent": turn.intent,
            "audio": "prerecorded"}


def officer_payload(turn: Turn) -> Dict[str, Any]:
    return {"turn_id": turn.id, "text": turn.text, "lang": turn.lang, "ts": _iso(turn.created_at),
            "origin": "human_officer"}


async def _speak_fixed(db: AsyncSession, session: Session, case: Case, state: State,
                       out: "Outbound") -> bool:
    """Speak an approved fixed script verbatim, or record that none is approved.

    Fixed scripts are never model-generated: the text comes only from an
    APPROVED record in ml.dialogue.scripts. Without one, nothing is said.
    """
    turns = await _turns(db, session.id)
    # The language the person last wrote in, as the turn path uses; else the session's.
    own = [t.lang for t in turns if t.speaker == "victim" and t.lang in ("hi", "en")]
    lang = own[-1] if own else (session.lang if session.lang in ("hi", "en") else "hi")
    text = fixed_script_text(state, lang)
    if not text:
        await audit.record(db, "fixed_script.unavailable", case_id=case.id, detail={"state": state.value})
        return False
    seq = max((t.seq for t in turns), default=0) + 1
    reply = Turn(id=str(uuid4()), session_id=session.id, seq=seq, speaker="assistant", text=text,
                 lang=lang, state=state.value, intent=STATE_INTENT[state], was_fallback=True,
                 review_status="approved_fixed_script", created_at=audit.now())
    db.add(reply)
    await db.flush()
    out.add("assistant.turn", assistant_payload(reply))
    out.add("transcript.line", transcript_payload(reply))
    return True


async def open_conversation(db: AsyncSession, session_id: str) -> "Outbound":
    """Speak the opening when the victim's socket first connects.

    The opening cannot be spoken at session creation: no socket exists yet to
    hear it. So it is spoken once, on the first victim connection to a session
    with no turns: S0 for a granted session, SH for a declined one. Only an
    approved fixed script is ever said; otherwise nothing is.
    """
    out = Outbound()
    session = await get_session_row(db, session_id)
    if session.ended_at is not None or await _turns(db, session_id):
        return out
    state = {State.S1_FREE_NARRATIVE.value: State.S0_OPENING,
             State.SH_HUMAN_HANDOFF.value: State.SH_HUMAN_HANDOFF}.get(session.state)
    if state is None:
        return out
    lang = session.lang if session.lang in ("hi", "en") else "hi"
    if not fixed_script_text(state, lang):
        return out  # unavailability was recorded at creation
    case = await case_for_session(db, session_id)
    await _speak_fixed(db, session, case, state, out)
    return out


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

    # S0 (or SH when consent is declined) is a fixed script. It is spoken on
    # the victim's first socket connection (open_conversation), and only from
    # an approved record; until then nothing is said and the reason is
    # recorded here. The AI disclosure is always delivered by the client from
    # `ai_disclosure` as well.
    lang_ok = lang if lang in ("hi", "en") else "hi"
    opening = State.SH_HUMAN_HANDOFF if consent == CONSENT_DECLINED else State.S0_OPENING
    if not fixed_script_text(opening, lang_ok):
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


#: The console-only audio measurements kept on a voice turn (PC-11).
ASR_QUALITY_KEYS = ("poor_audio", "low_asr_confidence", "speech_s", "duration_s")


def _asr_quality(asr: Dict[str, Any]) -> Dict[str, Any]:
    q = asr.get("quality") or {}
    out = {k: asr.get(k) for k in ASR_QUALITY_KEYS if k in asr}
    out.update({k: q.get(k) for k in ("snr_db", "clipping_ratio") if k in q})
    # Prosody measurements feed D4 (plan M12h): deviation from the caller's own baseline.
    if isinstance(asr.get("prosody"), dict):
        out["prosody"] = asr["prosody"]
        out["prosody_reasons"] = list(asr.get("prosody_reasons") or [])
    return out


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


async def _crisis_without_analysis(db: AsyncSession, session: Session, case: Case, consent: str,
                                   turn_id: str, out: "Outbound") -> None:
    """Crisis language where consent to AI analysis was not given.

    Raises the crisis alert and the takeover request, which put the case at
    the top of the queue. No band is set: scoring is not permitted. SX is
    said once on entering it, from an approved record only.
    """
    raised = await _upsert_crisis_alert(db, case, turn_id)
    if case.takeover_requested_at is None:
        case.takeover_requested_at = audit.now()
        await audit.record(db, "takeover.requested", case_id=case.id,
                           detail={"reason": "crisis_precheck", "turn_id": turn_id})
    case.needs_human = True
    if raised:
        await audit.record(db, "alert.raised", case_id=case.id,
                           detail={"type": "crisis", "severity": "critical", "turn_id": turn_id})
        out.add("alert.safety", {"alert_type": "crisis", "severity": "critical",
                                 "evidence_turn_ids": [turn_id], "requires_ack": True})
    if session.state != State.SX_CRISIS.value:
        session.state = State.SX_CRISIS.value
        await _speak_fixed(db, session, case, State.SX_CRISIS, out)


async def submit_turn(
    db: AsyncSession,
    session_id: str,
    text: str,
    lang: Optional[str] = None,
    victim_index: Optional[int] = None,
    asr: Optional[Dict[str, Any]] = None,
) -> Outbound:
    """Handle one victim turn: typed, or a transcribed voice turn (PC-11) carrying ``asr``
    measurements. Both take exactly the same path; see the module docstring for the order."""
    out = Outbound()
    started = time.perf_counter()
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
                  text=text, lang=lang, state=session.state, created_at=audit.now(),
                  asr_confidence=(asr or {}).get("asr_confidence"),
                  asr_quality=_asr_quality(asr) if asr else None)
    db.add(victim)
    try:
        await db.flush()
    except IntegrityError:
        raise Conflict("duplicate sequence number") from None
    turns.append(victim)
    out.add("transcript.line", transcript_payload(victim))

    # Consent not granted, or a completed human takeover, mutes every AI path:
    # no assessment, scoring, recommendation, extraction or dialogue below.
    # One exception without a human present: the synchronous crisis pre-check
    # (invariant 2; project lead decision 2026-10-02), a keyword match that
    # raises an alert for a person. It is not AI analysis and produces no score.
    # After a takeover the officer is already reading, so nothing runs.
    if consent != CONSENT_GRANTED or session.human_joined:
        if not session.human_joined and crisis_check(text)["crisis"]:
            await _crisis_without_analysis(db, session, case, consent, victim.id, out)
        case.updated_at = audit.now()
        out.add("session.status", status_payload(session, consent))
        return out

    # 2. synchronous crisis pre-check, before policy
    t_pre = time.perf_counter()
    pre = crisis_check(text)
    timings: Dict[str, Any] = {"safety_precheck": round(1000 * (time.perf_counter() - t_pre), 3)}

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
    fixed = False
    previous_state = session.state
    try:
        plan = plan_turn(session.state, slots, text, flags, get_provider(get_settings().LLM_PROVIDER))
        timings.update({k: v for k, v in (plan.get("timings_ms") or {}).items() if k != "safety_precheck"})
        next_state = plan["next_state"]
        intent = plan["intent"]
        assistant_text = plan["text"]
        fixed = bool(plan.get("fixed_script"))
        # A fixed script is said once, on entering its state. While SX, SH or
        # S9 holds, later turns are recorded for the officer and get silence,
        # never the same script again.
        if fixed and previous_state == next_state:
            assistant_text = None
    except FixedScriptUnavailable:
        decision = dialogue_next(session.state, slots, text, flags)
        next_state, intent = decision["next_state"], decision["intent"]
        await audit.record(db, "fixed_script.unavailable", case_id=case.id,
                           detail={"state": next_state, "turn_id": victim.id})

    session.state = next_state
    timings["reply_path"] = round(1000 * (time.perf_counter() - started), 3)
    latency.record(db, session_id, victim.id, {**timings, **latency.asr_service_timings(asr)})

    if assistant_text:
        reply = Turn(id=str(uuid4()), session_id=session_id, seq=next_seq + 1, speaker="assistant",
                     text=assistant_text, lang=flags["lang"], state=next_state, intent=intent,
                     was_fallback=True, review_status="approved_fixed_script" if fixed else "draft",
                     created_at=audit.now())
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


async def request_human(db: AsyncSession, session_id: str) -> Outbound:
    """The victim asked for a person. Always honoured, from any state."""
    out = Outbound()
    session = await get_session_row(db, session_id)
    case = await case_for_session(db, session_id)
    consent = await consent_for(db, session_id)
    previous = session.state
    if previous != State.SX_CRISIS.value:
        session.state = State.SH_HUMAN_HANDOFF.value
    case.needs_human = True
    await audit.record(db, "human.requested", case_id=case.id, dedupe_key=f"human.requested:{case.id}")
    # SH is spoken once, on entering handoff; never over the crisis script,
    # and never after the session ended (no officer can reach it then).
    if session.ended_at is None and previous not in (State.SX_CRISIS.value, State.SH_HUMAN_HANDOFF.value):
        await _speak_fixed(db, session, case, State.SH_HUMAN_HANDOFF, out)
    out.add("session.status", status_payload(session, consent))
    return out


async def end_session(db: AsyncSession, session_id: str) -> Tuple[Case, Outbound]:
    """End the session. Idempotent. S9 is spoken only from an approved record."""
    out = Outbound()
    session = await get_session_row(db, session_id)
    case = await case_for_session(db, session_id)
    consent = await consent_for(db, session_id)
    if session.ended_at is None:
        # S9 closes an ordinary intake once; it is not said over a crisis or
        # a handoff, and not repeated if the dialogue already reached it.
        shared = any(t.speaker == "victim" for t in await _turns(db, session_id))
        if shared and session.state not in (State.SX_CRISIS.value, State.SH_HUMAN_HANDOFF.value,
                                            State.S9_CLOSING.value):
            await _speak_fixed(db, session, case, State.S9_CLOSING, out)
        session.ended_at = audit.now()
        await audit.record(db, "session.ended", case_id=case.id)
    row = await audit.timeline(db, case.id, "under_review")
    if row is not None:
        out.add("timeline.update", audit.timeline_payload(row))
    out.add("session.status", status_payload(session, consent))
    return case, out


async def count_turns(db: AsyncSession, session_id: str) -> int:
    return int((await db.execute(select(func.count()).select_from(Turn).where(Turn.session_id == session_id))).scalar())
