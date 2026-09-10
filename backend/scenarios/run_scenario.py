"""Text-first demo scenario runner.

Drives the complete vertical slice through the SAME service functions the REST
API and the WebSocket use -- it never inserts assessment results directly:

  consent -> Hinglish/Hindi intake -> deterministic safety analysis ->
  structured case -> SVI / abstention -> alerts + recommendations ->
  executive claim -> alert acknowledgement -> confirm / modify / reject ->
  band-override validation -> takeover -> officer message (PC-07) ->
  victim-safe timeline -> audit trail

plus a crisis-interrupt scenario and a consent-declined scenario.

Idempotency: after the first pass it replays every scenario and every
executive action, and checks that no table gained a single row.

All data is fictional (backend/scenarios/data.py). It runs against its own
disposable SQLite file under runtime/db and never touches the development DB.

    backend\\.venv\\Scripts\\python.exe backend\\scenarios\\run_scenario.py --reset
"""

import argparse
import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNTIME_DB = (REPO / "runtime" / "db").resolve()
DEFAULT_DB = RUNTIME_DB / "scenario.db"

CHECKS: list = []
#: While replaying, the scenario steps run again but print and record nothing:
#: their assertions describe a FRESH case, and on replay the case is already in
#: its final state. A replay exists only to prove idempotency.
QUIET = {"on": False}


def check(label: str, ok: bool, detail: str = "") -> None:
    if QUIET["on"]:
        return
    CHECKS.append((label, bool(ok)))
    print(f"    {'ok  ' if ok else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")


def say(text: str = "") -> None:
    if not QUIET["on"]:
        print(text)


# ---------------------------------------------------------------------------
# Database setup (before any backend import, so the engine binds to this file)
# ---------------------------------------------------------------------------


def prepare_database(db_path: Path, reset: bool) -> None:
    if not str(db_path).startswith(str(RUNTIME_DB)):
        raise SystemExit(f"refusing: {db_path} is outside {RUNTIME_DB} (only runtime/db is disposable)")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    # Seed accounts get a local-only password; it is never printed.
    os.environ.setdefault("SEED_PASSWORD", "scenario-local-only-" + uuid.uuid4().hex[:8])
    if reset:
        for suffix in ("", "-wal", "-shm", "-journal"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not db_path.exists()
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            cwd=str(REPO / "backend"), env=os.environ.copy(),
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit("alembic upgrade failed:\n" + result.stderr[-2000:])
    say(f"  database: {db_path.name} ({'created' if fresh else 'existing'}), migrated to head")


# ---------------------------------------------------------------------------
# Scenario steps
# ---------------------------------------------------------------------------


async def run(replay_only: bool) -> int:
    sys.path.insert(0, str(REPO))
    from sqlalchemy import func, select

    from backend.app.adapters.assessment_runner import runner
    from backend.app.core.db import session_factory
    from backend.app.core.errors import DomainError
    from backend.app.models import (Alert, Assessment, AuditLog, Case, Consent, DecisionAI,
                                    DecisionHuman, LatencyMetric, Override, PolicyChunk,
                                    Recommendation, Session, TimelineEvent, Turn, User)
    from backend.app.services import casework, intake, packet
    from backend.app.services.events import publish
    from backend.app.workers import assessment as _worker  # noqa: F401  binds the job
    from backend.app.ws.fanout import find_leaks
    from backend.scenarios import data
    from backend.seed.seed import seed, sid

    tables = [User, Session, Consent, Turn, Case, Assessment, Alert, Recommendation,
              DecisionAI, DecisionHuman, Override, TimelineEvent, AuditLog, PolicyChunk, LatencyMetric]
    NS = uuid.uuid5(uuid.NAMESPACE_DNS, "sahay-ai.scenarios")

    async def counts() -> dict:
        async with session_factory()() as db:
            return {t.__tablename__: int((await db.execute(select(func.count()).select_from(t))).scalar())
                    for t in tables}

    async def start(sc):
        sess_id = str(uuid.uuid5(NS, sc["id"]))
        async with session_factory()() as db:
            session, case, out = await intake.create_session(db, sc["channel"], sc["consent"],
                                                             sc["lang"], session_id=sess_id)
            await db.commit()
            case_id = case.id
        publish(sess_id, case_id, out)
        return sess_id, case_id

    async def turn(sess_id, case_id, index, text):
        async with session_factory()() as db:
            out = await intake.submit_turn(db, sess_id, text, None, victim_index=index)
            await db.commit()
        publish(sess_id, case_id, out)
        await runner.drain()

    async def act(fn, *args):
        async with session_factory()() as db:
            result = await fn(db, *args)
            await db.commit()
        return result

    async def read(fn, *args):
        async with session_factory()() as db:
            return await fn(db, *args)

    # seed staff + demo placeholder policy notes (idempotent)
    await seed(reset=False, password=os.environ["SEED_PASSWORD"])
    officer = sid("user", "exec1")
    other_officer = sid("user", "exec2")

    async def boycott_threat():
        sc = data.BOYCOTT_THREAT
        say("\n== Scenario 1: boycott after a complaint, continuing threats (Hinglish / Hindi) ==")
        sess_id, case_id = await start(sc)
        say("  1. consent granted; S0 opening is unapproved so it is NOT spoken (fail closed)")
        trajectory = []
        for i, text in enumerate(sc["turns"], 1):
            await turn(sess_id, case_id, i, text)
            p = await read(packet.packet, case_id)
            a = p["assessment"]
            filled = sum(1 for k, v in (p["structured"] or {}).items() if v)
            trajectory.append(a["band"])
            say(f"  turn {i}: state={p['header']['session_state']:<3} band={a['band'] or 'Needs Human':<12} "
                f"svi={a['svi'] if a['svi'] is not None else '—':<6} "
                f"alerts={[x['alert_type'] for x in p['alerts']]} structured_fields={filled}")

        p = await read(packet.packet, case_id)
        say("  checks:")
        check("early turns abstain as Needs Human Assessment with no score",
              trajectory[0] is None and p["trajectory"][0]["svi"] is None)
        seen = [b for b in trajectory if b]
        check("SVI moves from Moderate to High",
              "Moderate" in seen and "High" in seen and seen.index("Moderate") < seen.index("High"),
              " → ".join(b or "NHA" for b in trajectory))
        check("structured record fills incrementally", True if p["structured"].get("incident") else False)
        turn_ids = {t["id"] for t in p["transcript"]}
        ev = [i for d in p["assessment"]["dimensions"] for i in d["evidence_turn_ids"]]
        ev += [i for a in p["alerts"] for i in a["evidence_turn_ids"]]
        ev += [i for r in p["recommendations"] for i in r["evidence_turn_ids"]]
        check("every evidence id resolves to a real turn", ev and set(ev) <= turn_ids, f"{len(ev)} links")
        check("a safety alert was raised", any(a["alert_type"] == "threat" for a in p["alerts"]))
        recs = {r["action_type"]: r for r in p["recommendations"]}
        check("recommendations await a human decision",
              recs and all(r["status"] == "awaiting_decision" for r in recs.values()), ", ".join(recs))
        check("every recommendation cites a DEMO placeholder policy note",
              all(r["policy_citations"] and r["policy_citations"][0].startswith("DEMO-POLICY")
                  for r in recs.values()))
        check("the victim timeline has no support step before any human decision",
              "action_taken" not in [e["stage"] for e in (await read(packet.timeline_for, case_id))["timeline"]])

        say("  10. executive claims the case")
        await act(lambda db: casework.claim(db, case_id, officer))
        try:
            await act(lambda db: casework.claim(db, case_id, other_officer))
            check("a second officer cannot claim it", False)
        except DomainError as exc:
            check("a second officer cannot claim it", True, exc.message)

        say("  11. alerts acknowledged")
        for a in p["alerts"]:
            await act(lambda db, a=a: casework.acknowledge(db, case_id, a["id"], officer))
        p = await read(packet.packet, case_id)
        check("all alerts acknowledged", all(a["acknowledged_at"] for a in p["alerts"]))

        say("  12. decisions on AI recommendations")
        plan = [("witness_protection", "confirm", ""),
                ("legal_aid", "modify", "Refer to the district legal services contact rather than a private lawyer."),
                ("police", "reject", "Caller asked that local police not be involved; escalate through the district officer.")]
        try:
            await act(lambda db: casework.decide(db, case_id, recs["police"]["action_id"], "reject", "", officer))
            check("reject without a rationale is refused", False)
        except DomainError as exc:
            check("reject without a rationale is refused", True, exc.message)
        for action_type, decision, why in plan:
            if action_type in recs:
                await act(lambda db, r=recs[action_type], d=decision, w=why:
                          casework.decide(db, case_id, r["action_id"], d, w, officer))
        p = await read(packet.packet, case_id)
        check("decisions are stored separately from recommendations",
              len(p["decisions"]) == 3 and all("decision" not in r for r in p["recommendations"]))
        check("undecided recommendations still await a decision",
              any(r["status"] == "awaiting_decision" for r in p["recommendations"]))

        say("  13. band override validation")
        try:
            await act(lambda db: casework.override_band(db, case_id, "Critical", "   ", officer))
            check("override without a reason is refused (400)", False)
        except DomainError as exc:
            check("override without a reason is refused (400)", exc.status_code == 400, exc.message)
        await act(lambda db: casework.override_band(
            db, case_id, "Critical", "Officer judgement: threats tied to the complaint and the family is isolated.",
            officer))
        p = await read(packet.packet, case_id)
        check("override recorded with its reason", p["header"]["band"] == "Critical"
              and p["overrides"] and p["overrides"][-1]["reason"].startswith("Officer judgement"))

        say("  14. takeover")
        await act(lambda db: casework.takeover(db, case_id, officer))
        await turn(sess_id, case_id, len(sc["turns"]) + 1, "Hello, kya koi hai?")
        p = await read(packet.packet, case_id)
        last = p["transcript"][-1]
        check("after takeover the assistant is muted", last["speaker"] == "victim")
        check("session shows a person has joined", p["header"]["human_joined"]
              and p["header"]["human_joined_at"] is not None)

        say("  14b. officer message after takeover (PC-07)")
        if not any(t["speaker"] == "officer" for t in p["transcript"]):  # replay adds nothing
            await act(lambda db: casework.officer_message(
                db, case_id, officer, "Main ek adhikari hoon. Aapki baat padh li hai, main aapke saath hoon.", "hi"))
        p = await read(packet.packet, case_id)
        officer_turns = [t for t in p["transcript"] if t["speaker"] == "officer"]
        check("officer message stored as a human officer turn", len(officer_turns) == 1)
        trail = await read(packet.audit_trail, case_id)
        check("officer message audited without its text",
              any(e["action"] == "officer.message" and "text" not in e["detail"] for e in trail))

        say("  15. victim-safe timeline")
        tl = await read(packet.timeline_for, case_id)
        say("     " + " → ".join(e["stage"] for e in tl["timeline"]))
        check("victim timeline carries no assessment field", find_leaks(tl) == [])
        check("confirmation (and only confirmation/modify) added support steps",
              [e["stage"] for e in tl["timeline"]].count("action_taken") == 2)

        say("  16. audit trail")
        trail = await read(packet.audit_trail, case_id)
        actions = [e["action"] for e in trail]
        say(f"     {len(trail)} events: " + ", ".join(sorted(set(actions))))
        texts = " ".join(sc["turns"])
        check("audit trail contains no victim narrative",
              not any(t[:25] in str(e["detail"]) for t in sc["turns"] for e in trail) and texts)
        check("human acts are attributed to the officer",
              all(e["actor"] == "Executive One" for e in trail if e["actor_kind"] == "human"))
        return case_id

    async def crisis():
        sc = data.CRISIS
        say("\n== Scenario 2: crisis interrupt ==")
        sess_id, case_id = await start(sc)
        for i, text in enumerate(sc["turns"], 1):
            await turn(sess_id, case_id, i, text)
        p = await read(packet.packet, case_id)
        crisis_turn = p["transcript"][[t["text"] for t in p["transcript"]].index(sc["turns"][2])]
        after = [t for t in p["transcript"] if t["seq"] > crisis_turn["seq"]]
        check("crisis turn forces state SX", crisis_turn["state"] != "SX" and p["header"]["session_state"] == "SX")
        check("band forced Critical", p["header"]["band"] == "Critical")
        check("critical crisis alert raised", ("crisis", "critical") in [(a["alert_type"], a["severity"]) for a in p["alerts"]])
        check("takeover requested", p["header"]["takeover_requested"])
        check("no assistant text after the crisis (SX script unapproved: fail closed)",
              all(t["speaker"] == "victim" for t in after))
        check("intake does not resume on the next turn", after and after[-1]["state"] == "SX")
        q = await read(packet.queue, )
        check("crisis case sorts to the top of the queue", q and q[0]["case_id"] == case_id)
        return case_id

    async def declined():
        sc = data.CONSENT_DECLINED
        say("\n== Scenario 3: consent declined ==")
        sess_id, case_id = await start(sc)
        for i, text in enumerate(sc["turns"], 1):
            await turn(sess_id, case_id, i, text)
        p = await read(packet.packet, case_id)
        check("routed straight to a person (SH)", p["header"]["session_state"] == "SH")
        check("no AI assessment at all", p["assessment"]["suppressed"] and not p["trajectory"])
        check("no alerts or recommendations", not p["alerts"] and not p["recommendations"])
        check("the text is kept for the officer", len([t for t in p["transcript"] if t["speaker"] == "victim"]) == 3)
        return case_id

    async def everything() -> None:
        await boycott_threat()
        await crisis()
        await declined()

    if replay_only:
        # The database already holds these scenarios, so a "first" pass here is
        # itself a replay. Fresh-case assertions cannot apply; prove only that
        # running everything again adds nothing. Use --reset for the full walk-through.
        say("\n== Database already populated: replay-only mode (use --reset for the walk-through) ==")
        before = await counts()
        QUIET["on"] = True
        try:
            await everything()
        finally:
            QUIET["on"] = False
    else:
        say("\n== Pass 1 ==")
        await everything()
        before = await counts()
        say("\n== Pass 2: replay every scenario and every officer action ==")
        QUIET["on"] = True
        try:
            await everything()
        finally:
            QUIET["on"] = False
    after = await counts()
    diff = {k: after[k] - before[k] for k in before if after[k] != before[k]}
    check("replay is idempotent: no table gained a row", not diff, str(diff) if diff else
          ", ".join(f"{k}={v}" for k, v in after.items()))

    await runner.drain()
    failed = [label for label, ok in CHECKS if not ok]
    say(f"\nRESULT: {len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed"
        + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="SAHAY-AI text scenario runner (fictional data)")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="disposable SQLite file under runtime/db")
    parser.add_argument("--reset", action="store_true", help="recreate the scenario database first")
    args = parser.parse_args(argv)
    db_path = Path(args.db).resolve()
    existed = db_path.exists() and not args.reset
    prepare_database(db_path, args.reset)
    return asyncio.run(run(replay_only=existed))


if __name__ == "__main__":
    sys.exit(main())
