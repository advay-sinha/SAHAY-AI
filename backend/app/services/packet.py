"""Read models: live queue, escalation packet, audit trail, victim timeline.

The packet follows HANDOVER.md section 14 (ten sections). Rules it enforces:
  * the score is never alone: breakdown, confidence and the provisional-weights
    flag travel with it;
  * Needs Human Assessment carries NO score — svi and band are null, there is
    no hidden number anywhere in the assessment section;
  * AI recommendations and human decisions are separate lists;
  * every evidence id refers to a turn that is in the transcript.

The queue carries no narrative text: a privacy-safe preview is codes only.
The victim timeline is built from an allowlist projection and contains no
assessment field (services/timeline.py).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ml.svi.dimensions import DIMENSION_LABELS, DIMENSION_ORDER, WEIGHTS, WEIGHTS_ARE_PROVISIONAL

from ..core.errors import NotFound
from ..models import (
    Alert,
    Assessment,
    AuditLog,
    Case,
    Consent,
    DecisionHuman,
    Override,
    Recommendation,
    Session,
    TimelineEvent,
    Turn,
    User,
)
from .timeline import victim_timeline

BAND_RANK = {"Critical": 0, "High": 1, None: 2, "Moderate": 3, "Low": 4}  # None = Needs Human


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _names(db: AsyncSession) -> Dict[str, str]:
    return {u.id: u.display_name or u.username for u in (await db.execute(select(User))).scalars()}


async def _consents(db: AsyncSession) -> Dict[str, str]:
    rows = (await db.execute(select(Consent).order_by(Consent.created_at))).scalars()
    return {c.session_id: c.status for c in rows}


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


async def queue(db: AsyncSession) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    names = await _names(db)
    consents = await _consents(db)
    sessions = {s.id: s for s in (await db.execute(select(Session))).scalars()}
    alerts_by_case: Dict[str, List[Alert]] = {}
    for a in (await db.execute(select(Alert))).scalars():
        alerts_by_case.setdefault(a.case_id, []).append(a)

    items = []
    for case in (await db.execute(select(Case).where(Case.status != "closed"))).scalars():
        s = sessions.get(case.session_id)
        alerts = alerts_by_case.get(case.id, [])
        unacked_critical = any(a.severity == "critical" and a.acknowledged_at is None for a in alerts)
        items.append({
            "case_id": case.id,
            "reference": case.reference,
            "language": s.lang if s else None,
            "channel": s.channel if s else None,
            "wait_seconds": int((now - _aware(case.created_at)).total_seconds()),
            "session_state": s.state if s else None,
            "session_ended": bool(s and s.ended_at),
            "band": case.band,
            "needs_human_assessment": case.band is None,
            "consent": consents.get(case.session_id, "pending"),
            "status": case.status,
            "assigned_to": names.get(case.claimed_by) if case.claimed_by else None,
            "assigned_officer_id": case.claimed_by,
            "takeover_requested": case.takeover_requested_at is not None,
            "alerts": [{"alert_type": a.type, "severity": a.severity,
                        "acknowledged": a.acknowledged_at is not None} for a in alerts],
            "unacknowledged_critical": unacked_critical,
        })

    # Critical unacknowledged alerts first, then takeover requests, then band,
    # then longest waiting.
    items.sort(key=lambda i: (
        0 if i["unacknowledged_critical"] else 1,
        0 if i["takeover_requested"] else 1,
        BAND_RANK.get(i["band"], 2),
        -i["wait_seconds"],
    ))
    return items


# ---------------------------------------------------------------------------
# Escalation packet
# ---------------------------------------------------------------------------


def _assessment_section(latest: Optional[Assessment], consent: str) -> Dict[str, Any]:
    if consent == "declined":
        return {"suppressed": True, "reason": "consent declined — no AI assessment",
                "svi": None, "band": None, "needs_human": True, "dimensions": []}
    if latest is None:
        return {"suppressed": False, "svi": None, "band": None, "needs_human": True,
                "reason": "not yet assessed", "dimensions": [], "overrides_applied": [],
                "abstention_reasons": [], "aggregate_confidence": None,
                "weights_are_provisional": WEIGHTS_ARE_PROVISIONAL}
    needs_human_no_score = latest.band is None
    norm = latest.normalization or {}
    unavailable = set(norm.get("structurally_unavailable") or [])
    denominator = norm.get("weight_denominator") or 1.0
    dims = []
    for d in DIMENSION_ORDER:
        v = (latest.breakdown or {}).get(d) or {}
        dims.append({
            "dimension": d, "label": DIMENSION_LABELS[d], "weight": WEIGHTS[d],
            # PC-08: a structurally unavailable dimension is shown as such,
            # never as measured and never as zero.
            "available": d not in unavailable,
            "effective_weight": 0.0 if d in unavailable else round(WEIGHTS[d] / denominator, 6),
            # Under Needs Human Assessment the per-dimension numbers are withheld
            # too: evidence is shown, a score is not.
            "score": None if needs_human_no_score else v.get("score"),
            "confidence": v.get("confidence"),
            "evidence_turn_ids": list(v.get("evidence_turn_ids") or []),
            "basis": v.get("basis"),
        })
    return {
        "suppressed": False,
        "svi": None if needs_human_no_score else latest.svi,
        "band": latest.band,
        "needs_human": latest.needs_human,
        "aggregate_confidence": latest.aggregate_confidence,
        "overrides_applied": latest.overrides_applied or [],
        "abstention_reasons": latest.abstention_reasons or [],
        "cause": latest.cause,
        "dimensions": dims,
        "weights_are_provisional": WEIGHTS_ARE_PROVISIONAL,
        "scoring_version": latest.scoring_version or None,
        "normalization": latest.normalization or {},
        "cycle": latest.cycle_index,
    }


async def packet(db: AsyncSession, case_id: str) -> Dict[str, Any]:
    case = await db.get(Case, case_id)
    if case is None:
        raise NotFound("case not found")
    session = await db.get(Session, case.session_id)
    names = await _names(db)
    consent = (await _consents(db)).get(case.session_id, "pending")

    turns = list((await db.execute(select(Turn).where(Turn.session_id == case.session_id)
                                   .order_by(Turn.seq))).scalars())
    assessments = list((await db.execute(select(Assessment).where(Assessment.case_id == case_id)
                                         .order_by(Assessment.cycle_index))).scalars())
    latest = assessments[-1] if assessments else None
    alerts = list((await db.execute(select(Alert).where(Alert.case_id == case_id)
                                    .order_by(Alert.created_at))).scalars())
    recs = list((await db.execute(select(Recommendation).where(Recommendation.case_id == case_id)
                                  .order_by(Recommendation.created_at))).scalars())
    decisions = list((await db.execute(select(DecisionHuman).where(DecisionHuman.case_id == case_id)
                                       .order_by(DecisionHuman.created_at))).scalars())
    decided = {d.recommendation_id for d in decisions}
    overrides = list((await db.execute(select(Override).where(Override.case_id == case_id)
                                       .order_by(Override.created_at))).scalars())

    started = _aware(session.created_at) if session else None
    ended = _aware(session.ended_at) if session and session.ended_at else datetime.now(timezone.utc)
    assessment = _assessment_section(latest, consent)

    return {
        "header": {
            "case_id": case.id, "reference": case.reference,
            "language": session.lang if session else None,
            "channel": session.channel if session else None,
            "duration_seconds": int((ended - started).total_seconds()) if started else None,
            "consent": consent, "band": case.band, "band_source": case.band_source,
            "needs_human_assessment": case.band is None,
            "status": case.status, "session_state": session.state if session else None,
            "session_ended": bool(session and session.ended_at),
            "human_joined": bool(session and session.human_joined),
            "human_joined_at": _iso(session.human_joined_at) if session else None,
            "assigned_to": names.get(case.claimed_by) if case.claimed_by else None,
            "assigned_officer_id": case.claimed_by,
            "takeover_requested": case.takeover_requested_at is not None,
            "session_id": case.session_id,
        },
        "assessment": assessment,
        "alerts": [{
            "id": a.id, "alert_type": a.type, "severity": a.severity,
            "evidence_turn_ids": list(a.evidence_turn_ids or []),
            "requires_ack": a.requires_ack,
            "acknowledged_by": names.get(a.acknowledged_by) if a.acknowledged_by else None,
            "acknowledged_at": _iso(a.acknowledged_at),
        } for a in sorted(alerts, key=lambda a: (a.acknowledged_at is not None,
                                                  -{"critical": 3, "high": 2}.get(a.severity, 1)))],
        "structured": case.structured or {},
        "transcript": [{
            "id": t.id, "seq": t.seq,
            "speaker": t.speaker, "text": t.text, "lang": t.lang, "state": t.state,
            "intent": t.intent or None, "review_status": t.review_status or None,
            "ts": _iso(t.created_at),
        } for t in turns],
        "evidence": {d["dimension"]: d["evidence_turn_ids"] for d in assessment.get("dimensions", [])
                     if d["evidence_turn_ids"]},
        "trajectory": [{
            "cycle": a.cycle_index, "svi": a.svi if a.band is not None else None, "band": a.band,
            "needs_human": a.needs_human, "cause": a.cause, "trigger_turn_id": a.trigger_turn_id,
            "ts": _iso(a.created_at),
        } for a in assessments],
        "recommendations": [{
            "action_id": r.id, "action_type": r.action_type, "label": r.label,
            "rationale": r.rationale, "policy_citations": list(r.policy_citations or []),
            "confidence": r.confidence, "evidence_turn_ids": list(r.evidence_turn_ids or []),
            "status": "decided" if r.id in decided else "awaiting_decision",
        } for r in recs],
        "decisions": [{
            "id": d.id, "action_id": d.recommendation_id, "decision": d.decision,
            "rationale": d.rationale, "officer": names.get(d.officer_id, d.officer_id),
            "decided_at": _iso(d.created_at),
        } for d in decisions],
        "overrides": [{
            "id": o.id, "from_band": o.from_band, "to_band": o.to_band, "reason": o.reason,
            "officer": names.get(o.officer_id, o.officer_id), "at": _iso(o.created_at),
        } for o in overrides],
        "uncertainty": (latest.uncertainty if latest else {}) if consent != "declined"
                       else {"reason": "consent declined — no AI assessment"},
        "disclaimer": ("This assessment is an assistive prioritisation aid generated by an AI "
                       "system. It is not a clinical, legal or forensic determination. All "
                       "decisions rest with the reviewing officer."),
    }


# ---------------------------------------------------------------------------
# Audit and timeline
# ---------------------------------------------------------------------------


async def audit_trail(db: AsyncSession, case_id: str) -> List[Dict[str, Any]]:
    if await db.get(Case, case_id) is None:
        raise NotFound("case not found")
    names = await _names(db)
    rows = (await db.execute(select(AuditLog).where(AuditLog.case_id == case_id)
                             .order_by(AuditLog.created_at, AuditLog.id))).scalars()
    return [{
        "at": _iso(r.created_at), "actor_kind": r.actor_kind,
        "actor": names.get(r.actor_id, r.actor_id) if r.actor_id else "system",
        "action": r.action, "detail": r.detail or {},
    } for r in rows]


async def timeline_for(db: AsyncSession, case_id: str) -> Dict[str, Any]:
    case = await db.get(Case, case_id)
    if case is None:
        raise NotFound("case not found")
    # timeline_events is the authoritative victim-safe timeline (PC-03).
    rows = (await db.execute(select(TimelineEvent).where(TimelineEvent.case_id == case_id)
                             .order_by(TimelineEvent.created_at, TimelineEvent.id))).scalars()
    entries = [{"stage": r.stage, "label": r.label, "ts": _iso(r.created_at)} for r in rows]
    return victim_timeline(case.reference, entries)
