"""Executive actions on a case. Every one is a HUMAN act, recorded as such.

State machine for a case:   open -> claimed -> taken_over -> closed

  claim      open -> claimed, atomically (a conditional UPDATE), so two
             officers clicking at once cannot both win. The same officer
             claiming again is a no-op.
  ack        marks an alert acknowledged (PC-01): records officer and time;
             repeating is a no-op; never changes the assessment, the band or
             the victim timeline.
  decide     confirm / modify / reject ONE recommendation; one decision per
             recommendation; modify and reject need a rationale; only confirm
             and modify create the victim-safe "action_taken" timeline step.
  override   sets the band with a mandatory written reason (400 without one).
  takeover   claimed -> taken_over; mutes the assistant; sets
             human_joined_at; tells the victim a person has joined.
  message    PC-07: the claiming officer writes to the victim, only after
             takeover. Stored as a human-origin turn; never AI-generated.

decide, override, takeover and message require the case to be claimed by the
caller: the officer acting is the officer accountable. Acknowledging an alert
does not, so a safety alert never waits on assignment -- but an officer may not
acknowledge an alert on a case another officer has claimed (403).

All of these are executive acts. The supervisor view is read-only (PC-06); the
route layer refuses a supervisor token before any of this runs.

AI recommendations (recommendations + decisions_ai) and human decisions
(decisions_human) are separate tables and stay separate here.
"""

from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ml.dialogue.states import State

from ..core.errors import BadRequest, Conflict, Forbidden, NotFound
from ..models import Alert, Case, DecisionHuman, Override, Recommendation, Session, Turn
from . import audit
from ..core.enums import BANDS, DECISIONS
from .intake import MAX_TURN_CHARS, Outbound, consent_for, status_payload


async def _case(db: AsyncSession, case_id: str) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise NotFound("case not found")
    return case


def _require_owner(case: Case, officer_id: str) -> None:
    if case.claimed_by is None:
        raise Conflict("claim the case before acting on it")
    if case.claimed_by != officer_id:
        raise Conflict("this case is assigned to another officer")


async def claim(db: AsyncSession, case_id: str, officer_id: str) -> Tuple[Case, Outbound]:
    out = Outbound()
    case = await _case(db, case_id)
    if case.claimed_by == officer_id:
        return case, out  # idempotent
    if case.status not in ("open",):
        raise Conflict("this case cannot be claimed in its current state")
    now = audit.now()
    result = await db.execute(
        update(Case)
        .where(Case.id == case_id, Case.claimed_by.is_(None), Case.status == "open")
        .values(claimed_by=officer_id, claimed_at=now, status="claimed", updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise Conflict("this case was just claimed by another officer")
    await db.refresh(case)
    await audit.record(db, "case.claimed", case_id=case_id, actor_id=officer_id,
                       actor_kind=audit.ACTOR_HUMAN)
    row = await audit.timeline(db, case_id, "officer_assigned", actor_id=officer_id)
    if row is not None:
        out.add("timeline.update", audit.timeline_payload(row))
    return case, out


async def acknowledge(db: AsyncSession, case_id: str, alert_id: str, officer_id: str) -> Alert:
    case = await _case(db, case_id)
    if case.claimed_by is not None and case.claimed_by != officer_id:
        raise Forbidden("this case is assigned to another officer")
    alert = await db.get(Alert, alert_id)
    if alert is None or alert.case_id != case_id:
        raise NotFound("alert not found on this case")
    if alert.acknowledged_at is not None:
        return alert  # idempotent: the first acknowledgement stands
    now = audit.now()
    result = await db.execute(
        update(Alert)
        .where(Alert.id == alert_id, Alert.acknowledged_at.is_(None))
        .values(acknowledged_by=officer_id, acknowledged_at=now)
        .execution_options(synchronize_session=False)
    )
    await db.refresh(alert)
    if result.rowcount == 1:
        await audit.record(db, "alert.acknowledged", case_id=case_id, actor_id=officer_id,
                           actor_kind=audit.ACTOR_HUMAN,
                           detail={"alert_id": alert_id, "alert_type": alert.type, "severity": alert.severity},
                           dedupe_key=f"ack:{alert_id}:{now.isoformat()}")
    return alert


async def decide(
    db: AsyncSession, case_id: str, action_id: str, decision: str, rationale: Optional[str],
    officer_id: str,
) -> Tuple[DecisionHuman, Outbound]:
    out = Outbound()
    if decision not in DECISIONS:
        raise BadRequest("decision must be confirm, modify or reject")
    rationale = (rationale or "").strip()
    if decision in ("modify", "reject") and not rationale:
        raise BadRequest("a rationale is required to modify or reject a recommendation")

    case = await _case(db, case_id)
    _require_owner(case, officer_id)
    rec = await db.get(Recommendation, action_id)
    if rec is None or rec.case_id != case_id:
        raise NotFound("recommendation not found on this case")

    existing = (await db.execute(select(DecisionHuman).where(
        DecisionHuman.recommendation_id == action_id))).scalar_one_or_none()
    if existing is not None:
        if existing.decision == decision and (existing.rationale or "") == rationale:
            return existing, out  # idempotent repeat
        raise Conflict("this recommendation has already been decided")

    row = DecisionHuman(id=str(uuid4()), case_id=case_id, recommendation_id=action_id,
                        officer_id=officer_id, decision=decision, rationale=rationale,
                        created_at=audit.now())
    try:
        async with db.begin_nested():
            db.add(row)
    except IntegrityError:
        raise Conflict("this recommendation has already been decided") from None

    await audit.record(db, "decision.recorded", case_id=case_id, actor_id=officer_id,
                       actor_kind=audit.ACTOR_HUMAN,
                       detail={"recommendation_id": action_id, "action_type": rec.action_type,
                               "decision": decision})
    # Only a human confirming (or confirming a modified version) is an action.
    # The AI recommendation alone never reaches the victim's timeline, and the
    # label never names the pathway.
    if decision in ("confirm", "modify"):
        stage = await audit.timeline(db, case_id, "action_taken", f"action:{action_id}", actor_id=officer_id)
        if stage is not None:
            out.add("timeline.update", audit.timeline_payload(stage))
    return row, out


async def override_band(
    db: AsyncSession, case_id: str, band: str, reason: Optional[str], officer_id: str,
) -> Dict[str, Any]:
    reason = (reason or "").strip()
    if not reason:
        raise BadRequest("a written reason is required to override the band")
    if band not in BANDS:
        raise BadRequest("band must be Low, Moderate, High or Critical")
    case = await _case(db, case_id)
    _require_owner(case, officer_id)
    previous = case.band
    if case.band_source == "override" and previous == band:
        last = (await db.execute(
            select(Override).where(Override.case_id == case_id).order_by(Override.created_at.desc())
        )).scalars().first()
        if last is not None and last.reason == reason:
            # Identical repeat of the override in force: nothing new to record.
            return {"override_id": last.id, "case_id": case_id, "from_band": last.from_band,
                    "to_band": band, "reason": reason}
    now = audit.now()
    record = Override(id=str(uuid4()), case_id=case_id, officer_id=officer_id,
                      from_band=previous, to_band=band, reason=reason, created_at=now)
    db.add(record)
    case.band, case.band_source, case.updated_at = band, "override", now
    await db.flush()
    # The overrides table is authoritative; the audit entry is accountability.
    await audit.record(db, "band.override", case_id=case_id, actor_id=officer_id,
                       actor_kind=audit.ACTOR_HUMAN,
                       detail={"override_id": record.id, "from_band": previous, "to_band": band})
    return {"override_id": record.id, "case_id": case_id, "from_band": previous,
            "to_band": band, "reason": reason}


async def takeover(db: AsyncSession, case_id: str, officer_id: str) -> Tuple[Case, Outbound]:
    out = Outbound()
    case = await _case(db, case_id)
    _require_owner(case, officer_id)
    if case.status == "taken_over":
        return case, out  # idempotent
    if case.status != "claimed":
        raise Conflict("this case cannot be taken over in its current state")
    session = await db.get(Session, case.session_id)
    now = audit.now()
    case.status, case.taken_over_at, case.updated_at = "taken_over", now, now
    session.human_joined = True
    session.human_joined_at = now
    if session.state != State.SX_CRISIS.value:
        session.state = State.SH_HUMAN_HANDOFF.value
    await audit.record(db, "case.taken_over", case_id=case_id, actor_id=officer_id,
                       actor_kind=audit.ACTOR_HUMAN)
    # The victim learns a person has joined from session.status.human_joined
    # (and from officer messages, PC-07); takeover is not a timeline stage.
    out.add("session.status", status_payload(session, await consent_for(db, case.session_id)))
    return case, out


def check_officer(body_officer_id: Optional[str], principal_subject: str) -> None:
    """The contract carries officer_id in the body; it must be the caller."""
    if body_officer_id and body_officer_id != principal_subject:
        raise Forbidden("officer_id must be the signed-in officer")


async def officer_message(
    db: AsyncSession, case_id: str, officer_id: str, text: str, lang: Optional[str],
) -> Tuple[Turn, Outbound]:
    """PC-07: a human officer writes to the victim after taking over.

    Strict limits (lead decision 2026-09-11):
      * only the officer who has claimed the case, after a verified takeover
        (case taken_over, session.human_joined, human_joined_at set);
      * stored as a human-origin turn, audited without its text;
      * delivered as `officer.message` with origin "human_officer";
      * no assessment field; never generated or rephrased by the AI;
      * sending before takeover is a 409.
    Officer text is written by a person and does not pass through the AI
    output validator (docs/dialogue/STATES.md).
    """
    out = Outbound()
    text = (text or "").strip()
    if not text:
        raise BadRequest("empty message")
    if len(text) > MAX_TURN_CHARS:
        raise BadRequest("message too long")
    case = await _case(db, case_id)
    _require_owner(case, officer_id)
    session = await db.get(Session, case.session_id)
    if case.status != "taken_over" or not session.human_joined or session.human_joined_at is None:
        raise Conflict("take over the conversation before messaging the complainant")
    if session.ended_at is not None:
        raise Conflict("the session has ended")

    last_seq = (await db.execute(
        select(Turn.seq).where(Turn.session_id == session.id).order_by(Turn.seq.desc()))).scalars().first()
    turn = Turn(id=str(uuid4()), session_id=session.id, seq=(last_seq or 0) + 1, speaker="officer",
                text=text, lang=lang or session.lang, state=session.state, intent="",
                was_fallback=False, created_at=audit.now())
    try:
        async with db.begin_nested():
            db.add(turn)
    except IntegrityError:
        raise Conflict("another message was sent at the same moment; send again") from None
    await audit.record(db, "officer.message", case_id=case_id, actor_id=officer_id,
                       actor_kind=audit.ACTOR_HUMAN, detail={"turn_id": turn.id, "chars": len(text)})
    out.add("officer.message", {"turn_id": turn.id, "text": turn.text, "lang": turn.lang,
                                "ts": turn.created_at.isoformat(), "origin": "human_officer"})
    return turn, out
