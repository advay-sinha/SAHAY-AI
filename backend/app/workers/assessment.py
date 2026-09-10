"""Background assessment cycle.

Runs off the reply path through the local runner. For one case it:
  reads the turns -> runs the pure deterministic pipeline in a worker thread
  -> persists one assessment row per cycle -> updates the case band (with its
  cause) -> upserts alerts and recommendations -> publishes executive events.

It never speaks to the victim and never triggers the crisis interrupt: that is
the synchronous pre-check's job (docs/dialogue/STATES.md).

Idempotent: a cycle is keyed by (case, number of victim turns heard). Running
the same cycle twice writes nothing the second time. Alerts are unique per
(case, type) and recommendations per (case, pathway), so reprocessing a turn
never duplicates either.

Human authority: once an officer overrides the band, later cycles keep
assessing but do not replace the officer's band -- except to escalate to
Critical on a hard safety override, which always wins.
"""

from typing import Any, Dict, List
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ml.assessment import assess

from ..adapters.assessment_runner import runner
from ..adapters.retrieval import KeywordRetriever
from ..core.db import session_factory
from ..models import (
    Alert,
    Assessment,
    Case,
    DecisionAI,
    DecisionHuman,
    PolicyChunk,
    Recommendation,
    Session,
    Turn,
)
from ..services import audit
from ..services.intake import consent_for
from ..ws.hub import hub
from ..services.consent import CONSENT_GRANTED

SEVERITY_RANK = {"medium": 1, "high": 2, "critical": 3}
MODEL_VERSION = "text-lexicon-v1"


def _alert_event(kind: str, severity: str, evidence) -> Dict[str, Any]:
    """alert.safety payload. The alert kind is `alert_type`, not `type`: the
    frame's own `type` is the event name and must not be overwritten."""
    return {"alert_type": kind, "severity": severity,
            "evidence_turn_ids": list(evidence or []), "requires_ack": True}


def _dims_payload(dims: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """dimension.update shape: {D1..D9: {score, conf, evidence_turn_ids}}."""
    return {
        d: {"score": v.get("score"), "conf": v.get("confidence"),
            "evidence_turn_ids": list(v.get("evidence_turn_ids") or [])}
        for d, v in dims.items()
    }


async def run_cycle(case_id: str) -> None:
    events: List[tuple] = []
    factory = session_factory()
    async with factory() as db:
        case = await db.get(Case, case_id)
        if case is None:
            return
        session = await db.get(Session, case.session_id)
        consent = await consent_for(db, case.session_id)
        if consent != CONSENT_GRANTED:
            return  # consent declined or pending: no analysis, ever

        turns = list((await db.execute(
            select(Turn).where(Turn.session_id == case.session_id).order_by(Turn.seq)
        )).scalars())
        victim = [t for t in turns if t.speaker == "victim"]
        if not victim:
            return
        cycle = len(victim)
        exists = (await db.execute(select(Assessment.id).where(
            Assessment.case_id == case_id, Assessment.cycle_index == cycle))).first()
        if exists:
            return

        crisis_fired = session.state == "SX" or bool((await db.execute(select(Alert.id).where(
            Alert.case_id == case_id, Alert.type == "crisis"))).first())
        turn_dicts = [{"id": t.id, "speaker": t.speaker, "text": t.text, "state": t.state} for t in turns]

        # The slow path: pure CPU work, off the event loop.
        channel = session.channel
        result = await runner.in_thread(
            lambda: assess(turn_dicts, True, crisis_fired, channel=channel))

        trigger = victim[-1].id
        try:
            async with db.begin_nested():
                db.add(Assessment(
                    id=str(uuid4()), case_id=case_id, cycle_index=cycle, trigger_turn_id=trigger,
                    svi=result["svi"], band=result["band"], needs_human=result["needs_human"],
                    aggregate_confidence=result["aggregate_confidence"], breakdown=result["dims"],
                    overrides_applied=result["overrides_applied"],
                    abstention_reasons=result["abstention_reasons"], cause=result["cause"],
                    uncertainty=result["uncertainty"], pipeline_version=result["pipeline_version"],
                    scoring_version=result["scoring_version"], normalization=result["normalization"],
                    created_at=audit.now(),
                ))
        except IntegrityError:
            return  # another worker got here first; nothing to do

        # --- band, with its cause --------------------------------------
        new_band = result["band"]
        safety_escalation = new_band == "Critical" and bool(result["overrides_applied"])
        if case.band_source != "override" or safety_escalation:
            if case.band != new_band:
                await audit.record(db, "band.changed", case_id=case_id, detail={
                    "from": case.band, "to": new_band, "cause": result["cause"],
                    "trigger_turn_id": trigger, "cycle": cycle})
            case.band = new_band
            case.band_source = "ai" if new_band else case.band_source
        case.svi = result["svi"]
        case.needs_human = bool(result["needs_human"])
        case.structured = result["structured"] or {}
        case.updated_at = audit.now()

        if cycle == 1:
            await audit.timeline(db, case_id, "under_review")

        # --- alerts: one per (case, type) -------------------------------
        existing = {a.type: a for a in (await db.execute(
            select(Alert).where(Alert.case_id == case_id))).scalars()}
        for a in result["alerts"]:
            prior = existing.get(a["type"])
            if prior is None:
                try:
                    async with db.begin_nested():
                        db.add(Alert(id=str(uuid4()), case_id=case_id, type=a["type"],
                                     severity=a["severity"], evidence_turn_ids=a["evidence_turn_ids"],
                                     requires_ack=True, created_at=audit.now()))
                except IntegrityError:
                    continue
                await audit.record(db, "alert.raised", case_id=case_id,
                                   detail={"alert_type": a["type"], "severity": a["severity"], "cycle": cycle})
                events.append(("alert.safety", _alert_event(a["type"], a["severity"], a["evidence_turn_ids"])))
                continue
            prior.evidence_turn_ids = sorted(set(prior.evidence_turn_ids or []) | set(a["evidence_turn_ids"]))
            if SEVERITY_RANK.get(a["severity"], 0) > SEVERITY_RANK.get(prior.severity, 0):
                await audit.record(db, "alert.escalated", case_id=case_id, detail={
                    "alert_type": a["type"], "from": prior.severity, "to": a["severity"], "cycle": cycle})
                prior.severity = a["severity"]
                prior.acknowledged_by, prior.acknowledged_at = None, None  # needs a fresh ack
                events.append(("alert.safety", _alert_event(a["type"], a["severity"], prior.evidence_turn_ids)))

        # --- recommendations: one per (case, pathway) --------------------
        chunks = [{"citation": c.citation, "keywords": c.keywords, "source": c.source}
                  for c in (await db.execute(select(PolicyChunk))).scalars()]
        retriever = KeywordRetriever(chunks)
        recs = {r.action_type: r for r in (await db.execute(
            select(Recommendation).where(Recommendation.case_id == case_id))).scalars()}
        decided = {rid for (rid,) in (await db.execute(
            select(DecisionHuman.recommendation_id).where(DecisionHuman.case_id == case_id))).all()}

        for r in result["recommendations"]:
            hits = retriever.search(r["query"], limit=1)
            citations = [h["citation"] for h in hits]
            prior = recs.get(r["action_type"])
            if prior is None:
                rec_id = str(uuid4())
                try:
                    async with db.begin_nested():
                        db.add(Recommendation(
                            id=rec_id, case_id=case_id, action_type=r["action_type"], label=r["label"],
                            rationale=r["rationale"], policy_citations=citations,
                            confidence=r["confidence"], evidence_turn_ids=r["evidence_turn_ids"],
                            created_at=audit.now()))
                        await db.flush()
                        db.add(DecisionAI(
                            id=str(uuid4()), case_id=case_id, recommendation_id=rec_id,
                            proposed_action=r["action_type"], model_version=MODEL_VERSION,
                            payload={**r, "policy_citations": citations}, created_at=audit.now()))
                except IntegrityError:
                    continue
                await audit.record(db, "recommendation.proposed", case_id=case_id,
                                   detail={"action_type": r["action_type"], "cycle": cycle})
                events.append(("action.recommended", {
                    "action_id": rec_id, "action_type": r["action_type"], "rationale": r["rationale"],
                    "policy_citations": citations, "confidence": r["confidence"]}))
            elif prior.id not in decided:
                # Still awaiting a decision: keep the evidence current.
                prior.evidence_turn_ids = r["evidence_turn_ids"]
                prior.confidence = r["confidence"]

        await db.commit()

        session_id = case.session_id
        alerts_now = [_alert_event(a.type, a.severity, a.evidence_turn_ids)
                      for a in (await db.execute(select(Alert).where(Alert.case_id == case_id))).scalars()]
        summary = (f"{case.reference}: band {case.band or 'Needs Human Assessment'}; "
                   f"{len(alerts_now)} alert type(s)")

    # Publish AFTER commit, never while holding the transaction.
    hub.publish(session_id, "dimension.update", {
        "dims": _dims_payload(result["dims"]), "svi": result["svi"], "band": result["band"],
        "needs_human": result["needs_human"], "overrides_applied": result["overrides_applied"]})
    for event_type, payload in events:
        hub.publish(session_id, event_type, payload)
    if result["structured"]:
        hub.publish(session_id, "case.structured", _structured_payload(result["structured"]))
    hub.publish(session_id, "escalation.packet", {
        "case_id": case_id, "band": result["band"], "alerts": alerts_now, "summary": summary, "ready": True})


def _structured_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """case.structured (CONTRACTS.md section 3), values only; sources stay in the packet."""
    def val(field):
        v = record.get(field)
        return v.get("value") if isinstance(v, dict) else v

    return {
        "incident": val("incident"),
        "timeline": [{"stage": "incident", "label": t["value"], "ts": ""} for t in record.get("timeline", [])],
        "persons": [p["value"] for p in record.get("persons", [])],
        "threats": [t["value"] for t in record.get("threats", [])],
        "safety_now": val("safety_now"),
        "medical_need": val("medical_need"),
        "legal_status": val("legal_status"),
        "isolation": val("isolation"),
        "requested_support": val("requested_support"),
    }


runner.bind(run_cycle)
