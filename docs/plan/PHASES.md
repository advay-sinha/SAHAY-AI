# SAHAY-AI — Local-First 14-Day Build Plan

This plan replaces Docker/CI requirements for the MVP. Safety, dialogue, assessment-leakage and human-decision gates remain unchanged. Gates are dates; when a gate fails, cut features rather than move the gate.

## P0 — Day 1: contracts and local skeleton

- Freeze contracts, schema, SVI and dialogue states.
- Generate `ml/`, `backend/`, `frontend/`, `mobile/`, `data-scripts/`, `scripts/` and `runtime/` scaffolds.
- Configure SQLite through SQLAlchemy and deterministic database seeding.
- Create manual verification scripts.
- Establish separate local Git branches/worktrees per team.
- FastAPI health endpoint and React-to-FastAPI WebSocket echo work locally.
- Record external decisions before installing/downloading.

## P1 — Days 2–4: conversation gate

- Implement and test the 12-state dialogue policy, crisis pre-check and output validator.
- Review Hindi/English fixed scripts and prepare fallback audio.
- Implement text conversation first, then approved ASR/VAD integrations.
- Implement consent, language, Talk, Chat and persistent human-request controls.
- Build the console shell and two-sided transcript against fixtures.
- Start the fictional scenario corpus.

### Day 4 gate

A person speaks Hindi into the phone and the assistant answers aloud in about three seconds, driven by the deterministic state machine. Whole-utterance submission may be used if streaming is not ready. The crisis pre-check must already be testable.

## P2 — Days 5–8: assessment and escalation

- Run assessment through the local background runner, separate from the reply path.
- Implement detectors, acoustic features, SVI, abstention and hard overrides.
- Persist cases, turns, assessments, alerts, AI recommendations and human decisions in SQLite.
- Implement escalation packet, acknowledgement, confirm/modify/reject, band override and takeover.
- Implement victim-safe timeline and role-filtered fan-out.
- Use local retrieval with citations; external LLM remains optional behind a mock.

### Day 8 gate

Consent → Hindi conversation → live assessment → crisis interrupt → Critical alert → executive decision → takeover → victim-safe timeline. A full session must complete with the LLM disabled. Automated tests must prove assessment data cannot reach the victim client.

## P3 — Days 9–11: hardening and evaluation

- Complete the 60-session fictional evaluation corpus.
- Measure WER/CER, detector precision/recall/F1, critical-event miss rate and turn latency.
- Run guardrail red-team, noisy audio, reconnection and three-session tests.
- Add accessibility and error/offline states.
- Decide whether Docker/PostgreSQL/Redis/CI add more value than risk. Each requires explicit approval.

## P4 — Days 12–13: freeze and demo

- Feature freeze at Day 12 noon.
- Tag `v0.9-freeze`.
- Generate a clean demo database from a seed script.
- Test on the exact laptop and an outside Android phone.
- Record backup video.
- Rehearse the 90-second demonstration at least five times.
- Prepare evaluation, red-team, ethics and limitations material.

## P5 — Day 14: buffer

- Fix demo-critical defects only.
- Tag `v1.0-demo`.
- Rehearse from the tag on the actual machine and phone.

## Cut order

Supervisor view → case export → trajectory interactivity → web portal parity → English voice generation → native streaming refinements.

Never cut consent, crisis interrupt, role-filtered fan-out, evaluation, abstention or the human decision step.
