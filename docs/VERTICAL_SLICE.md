# Text-first vertical slice

Fictional intake turns → deterministic safety analysis → structured case →
SVI / abstention → alerts and recommendations → live executive queue → case
workspace → human decision → takeover → officer message → victim-safe timeline
→ audit trail.

Contract v2 (lead decisions PC-01 to PC-10, 2026-09-11) is applied: see
`docs/contracts/CONTRACTS.md` and `docs/contracts/PROPOSED_CHANGES.md`.

Local only: FastAPI, SQLite, an in-process assessment runner, keyword policy
retrieval, the mock LLM, and the React/Vite console. No external model or
service. The mobile app is deferred.

## Run it

```powershell
# the scenario walk-through, against its own disposable DB (runtime/db/scenario.db)
backend\.venv\Scripts\python.exe backend\scenarios\run_scenario.py --reset
# run it again: replay-only mode, proves no table gains a row
backend\.venv\Scripts\python.exe backend\scenarios\run_scenario.py

# the console against the dev DB
backend\.venv\Scripts\python.exe -m alembic upgrade head        # from backend\
$env:SEED_PASSWORD = "<local-only>"; backend\.venv\Scripts\python.exe backend\seed\seed.py
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1                                    # http://127.0.0.1:5173/login
```

The scenario runner drives the same service functions the REST API and the
WebSocket use; it never inserts assessment results directly. It covers a
boycott-and-threat case (Hinglish and Hindi), a crisis interrupt, and a
consent-declined case, then replays every step and every officer action.

## How the pieces fit

| Step | Where |
|---|---|
| Session, consent, text turns, human request, end | `backend/app/services/intake.py` (REST `/sessions`, WS `chat.message` / `request_human`) |
| Crisis pre-check, synchronous, before policy | `ml/guardrails/crisis_precheck.py` via `intake.submit_turn` |
| Dialogue policy; fixed scripts fail closed | `ml/dialogue/policy.py`, `backend/app/services/turn_loop.py` |
| Background assessment (pure pipeline in a thread) | `backend/app/workers/assessment.py`, `backend/app/adapters/assessment_runner.py` |
| Deterministic text pipeline | `ml/assessment.py`, `ml/nlp/{lexicons,detectors,extraction,langid,recommend}.py`, `ml/svi/` |
| Claim, acknowledge, decide, override, takeover, officer message | `backend/app/services/casework.py` |
| Frozen enumerations (PC-10) | `backend/app/core/enums.py` (mirrored in `frontend/src/types/contracts.ts`) |
| Queue, packet, audit, victim timeline | `backend/app/services/packet.py` |
| Role-filtered, non-blocking fan-out | `backend/app/ws/hub.py`, `backend/app/ws/fanout.py` |
| Console | `frontend/src/pages/{QueuePage,CasePage,AuditPage,SupervisorPage}.tsx`, `frontend/src/console/` |

## Behaviour worth knowing

- **Fixed scripts fail closed.** S0, S9, SX and SH are not approved, so the
  assistant says nothing in those states; the event is audited as
  `fixed_script.unavailable`. The AI disclosure reaches the client through
  `ai_disclosure` in the session response, not through an unreviewed script.
- **Question text is draft.** Licensed questions (English verbatim from
  STATES.md, Hindi drafted) and the S1 acknowledgement are sent in this
  fictional-data slice and marked `review_status: draft` in the transcript.
  They must be reviewed before any real use.
- **Crisis** forces SX, a critical crisis alert, a takeover request and — when
  scoring is permitted — band Critical. Intake never resumes.
- **Consent declined** keeps the text for a person to read and runs no AI
  analysis at all: no score, no alerts from the pipeline, no recommendations.
- **Abstention.** Early turns, poor or unreadable input, low language
  confidence and conflicting safety statements return Needs Human Assessment
  with no score anywhere — not in the packet, the queue or the trajectory.
- **Human authority.** A band override holds against later assessments, except
  that a hard safety override (imminent danger, crisis) still escalates to
  Critical. Only a human confirm or modify adds the victim-safe
  `action_taken` timeline step, and its label never names the pathway.
- **Storage (PC-03).** Overrides live in `overrides`, victim-safe stages in
  `timeline_events` (15 tables). Each write is also recorded in the append-only
  `audit_log` for accountability; the audit log is not the timeline.
- **Supervisor view is read-only (PC-06).** Every console write is
  executive-only; a supervisor token gets 403.
- **Alert acknowledgement (PC-01)** records the officer and time, is
  idempotent, and changes neither the assessment nor the victim timeline.
- **Officer messages (PC-07).** Only after takeover, only by the officer who
  claimed the case; delivered to the victim as `officer.message` with origin
  `human_officer`; stored as an officer turn; audited without the text.
- **Session response (PC-09).** `POST /sessions` returns `session_token` (the
  victim credential for that session only) and a `ws_url` with no token. The
  slice's clients append `?token=` themselves (transitional, PC-05).
- **Idempotency** is enforced by unique keys: turns `(session, seq)`,
  assessments `(case, cycle)`, alerts `(case, type)`, recommendations
  `(case, pathway)`, one AI proposal and one human decision per
  recommendation, `timeline_events (case, dedupe_key)` for timeline stages,
  and `audit_log.dedupe_key` for acknowledgements.

## What this does not claim

The detectors are v1 development lexicons with severity tiers — not a trained
model, not validated, not a diagnosis. Acoustic distress (D4) is
structurally unavailable on the typed channels and is never estimated or
zeroed. The SVI renormalises over the other eight weights (÷ 0.88, PC-08) and
the console says so. An audio channel without acoustic measurement abstains.
The SVI weights are provisional. The policy notes are demo placeholders with
placeholder ids, not official policy.

Deferred contract items (PC-04 queue push, PC-06 supervisor actions, the PC-05
socket auth handshake) are recorded in `docs/contracts/PROPOSED_CHANGES.md`.
