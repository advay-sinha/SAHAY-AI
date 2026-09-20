---
name: phase-gate-check
description: Use when checking readiness for the Day 4, Day 8 or Day 12 gate, or when deciding whether to proceed to the next phase. Defines the criteria, how to verify each, and the cut-scope rule.
---

# Phase gate check

Gates are dates, not milestones. They do not move. When a gate fails, scope is cut — the phase is never extended, because Days 9–11 (evaluation, hardening, resilience) are what make the submission credible and they are the first thing a slipping team sacrifices.

## Verification principle

Verify by running, not by reading. "The code looks right" is not a pass. Every criterion is PASS, FAIL, or CANNOT VERIFY with evidence attached.

## Day 4 — the conversation exists

The assistant answers out loud, in Hindi, correctly, in about three seconds, driven by the deterministic state machine. Nothing else counts on Day 4 — not the SVI, not the console, not the packet.

Also decide at this gate: native app or mobile web. It is the last cheap moment to make that call.

## Day 8 — full session and escalation

Consent → AI conversation → live assessment → crisis interrupt → Critical alert → executive opens the packet, decides on recommendations, takes over → victim timeline updates. Plus the two safety invariants: role fan-out holds, crisis interrupt is unconditional. Plus LLM-off mode completes a full session.

## Day 12 — freeze

Tag, backup video, APK on an outside phone, all ten scenarios passing across languages and conditions, evaluation table, red-team table.

## When a gate fails

1. Say so plainly in the first sentence. Do not lead with what does work.
2. Order the failures by how much other work they block.
3. Recommend cuts. Candidates in order: optional push-to-talk, supervisor view, case export, trajectory interactivity, web portal parity, second language, native app (fall back to mobile web).
4. Never recommend: cutting evaluation, cutting the crisis interrupt, cutting role-filtered fan-out, cutting the consent flow, cutting the human decision step. These are what the project is.
