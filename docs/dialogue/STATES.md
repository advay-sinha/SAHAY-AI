# Dialogue states, licensed questions and fixed scripts

Changes here are `type:dialogue`: **two reviewers**, one of them running the `dialogue-safety-reviewer` agent, and the code change in the same commit. This file defines what the system says to a victim.

## Principle

The assistant is a **bounded intake instrument, not a chatbot**. A deterministic state machine chooses one approved intent. The LLM only phrases that intent. `guardrails.validate()` checks the output before synthesis; on failure the pre-written fallback is spoken. Every intent has a fallback in Hindi and English, so the system runs fully with the LLM disabled.

## States

| State | Purpose | Licensed question | Slots |
|---|---|---|---|
| **S0 OPENING** | Fixed script, pre-recorded. Identifies the assistant as an AI, states that a human officer reviews everything, states the right to a human at any time, invites the person to speak in their own words | — | — |
| **S1 FREE NARRATIVE** | Listen. Acknowledge briefly and neutrally. Do not interrupt, do not probe | none | incident, persons, location, time (extracted, not asked) |
| **S2 IMMEDIATE SAFETY** | The most important question in the intake | Are you safe right now — can the person who harmed you reach you? | safety_now, proximity_of_threat |
| **S3 MEDICAL NEED** | Never asks for detail about an injury | Does anyone need medical help right now? | medical_need, urgency |
| **S4 WHO AND WHEN** | Only fills gaps the narrative left. **Skipped if already answered** | who was involved / when did this happen | persons, relationship, when, where |
| **S5 ONGOING THREAT** | Continuing pressure and witness risk | Are the threats still continuing — has anyone told you not to complain? | threat_ongoing, intimidation, witness_concern |
| **S6 SUPPORT NETWORK** | Isolation, boycott, displacement | Is there someone with you right now? | isolation, displacement, support_person |
| **S7 EXISTING ACTION** | Case status | Has a complaint or FIR been filed — do you have legal help? | fir_status, legal_help |
| **S8 WHAT THEY WANT** | Their stated need is a first-class field | What help are you looking for right now? | requested_support |
| **S9 CLOSING** | Fixed script, pre-recorded. Confirms the account is recorded, gives the reference number, states what happens next. **No promises of outcome** | — | — |
| **SX CRISIS INTERRUPT** | Reachable from any state, unconditionally. Fixed pre-approved script. Raises Critical, requests immediate human takeover. **Does not return to intake** | — | — |
| **SH HUMAN HANDOFF** | Reachable from any state on request or escalation. Confirms transfer, holds the session for the executive | — | — |

## Rules

- States are **skippable and reorderable**. If the free narrative answered S4, skip it. Asking what was just said is the fastest way to lose a distressed person's trust.
- Target **8–12 turns** total. This is a first contact, not an interview.
- The **chat channel uses the identical state machine**; text turns skip ASR and TTS.
- Only **SX** may interrupt the flow, and only from the fast safety pre-check — never from the full assessment pipeline, and never from a model decision.
- **Officer messages in SH (PC-07, lead decision 2026-09-11).**
  - After a verified takeover, the claiming officer may write to the complainant: `POST /cases/{id}/messages`, delivered as `officer.message` with origin `human_officer`.
  - The officer writes this text, so it does **not** pass through the AI output validator or the state machine. No AI may generate, rephrase or send it.
  - The assistant stays muted. An officer message never restarts intake, and it never carries a score, band or alert.

## Writing rules for every utterance

One sentence. Plain words. One question, and only the one the state licenses.

**Never:** advice (legal, medical, procedural), diagnosis, promises about outcomes / timelines / arrest / compensation, requests for graphic or forensic detail, asking a victim "why", blaming or testing the account, or minimising comfort language ("calm down", "don't worry", "be strong", "I understand how you feel", "at least…") in either language.

## Fixed scripts — TODO before Day 3

`S0`, `S9` and `SX` must be written in Hindi and English, reviewed, and pre-synthesised to WAV. They are **never model-generated**.

**`SX` must be read by a counsellor or psychology faculty member before Day 8, and that review named in the deck.** It acknowledges, states plainly that a person will speak with them now, and asks them to stay. Nothing else — no advice, no assessment, no questions.

> Status: **not yet written.** Owner: Team A / A2. Blocks Backend and Frontend demos.
>
> The decisions that must be settled before any wording is drafted are listed in
> `docs/dialogue/FIXED_SCRIPTS_REVIEW.md`. The code fails closed until a script
> is recorded with a named reviewer and a review date.
>
> Task 5C candidate wording (S0, S9, SH, SX; English and Hindi) is pending review
> in `FIXED_SCRIPTS_CANDIDATE_REVIEW.md`. Task 5D-L lets that exact wording appear
> as **provisional, unreviewed, local-demo-only, text-only** turns behind a
> default-off development/test flag; it approves nothing, and
> `fixed_scripts_ready` stays false. See the exception in `FIXED_SCRIPTS_REVIEW.md`.
