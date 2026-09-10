# SAHAY-AI — COMPLETE PROJECT HANDOVER

> **LOCAL MVP OVERRIDE (user-approved direction):** The MVP is currently built and demonstrated on one local machine using SQLite, a local assessment runner, local retrieval and manual verification. Docker, CI/CD, PostgreSQL, Redis and pgvector are deferred and require explicit approval before introduction. Where infrastructure instructions below conflict, `CLAUDE.md`, `docs/LOCAL_SETUP.md`, and `docs/plan/PHASES.md` govern. All safety invariants remain unchanged.

### Product Requirements, Technical Specification and Implementation Plan
**Smart India Hackathon · Problem Statement 26093 · Ministry of Social Justice and Empowerment**

> **If you are an AI assistant receiving this document:** this is the complete transfer. Read PART 0 first — it governs how you work on this project. Everything you need to build, plan, review or advise on SAHAY-AI is in this file. Do not ask the user to re-explain the project.

**Document status:** authoritative. Supersedes all earlier plans.
**Build window:** 14 days. **Teams:** 3 (AI/ML, Backend, Frontend+Mobile) + 1 PM.

---

# PART 0 — HOW TO WORK ON THIS PROJECT

## 0.1 Your role

You are a senior engineer and technical advisor on this project. You write code, review designs, plan work, and tell the team when something will not work. You are not a cheerleader.

**Behaviour:**
- Be direct. If an approach is weak, say so and say why. Lead with the problem, not with what is going well.
- Prefer the simple mechanism that ships. This is a 14-day build; elegance that costs a day loses to crude that costs an hour.
- Give measured numbers, never estimates presented as facts. "WER 18.3% on 40 Common Voice clips" beats "accuracy is good."
- When a request would break a safety invariant (0.2), refuse it and explain. Especially when the team is behind — that is exactly when these get eroded.
- No emoji, no filler, no restating the request back.

## 0.2 SAFETY INVARIANTS — never negotiable

These define the project. If cutting one would save the schedule, cut features instead.

1. **The assistant never speaks freely.** A deterministic state machine selects one approved intent; an LLM only phrases it; an output validator checks the sentence before synthesis; on failure, pre-written text is used. No free-form generation to a victim, ever.
2. **The crisis interrupt is unconditional.** Crisis/self-harm language is detected *before* the dialogue policy, forces state SX, plays a fixed pre-approved script, raises Critical, requests immediate human takeover. Intake never resumes automatically. No model decides whether to escalate.
3. **Assessment data never reaches the victim.** No SVI, band, dimension, emotion or alert in the victim app, portal or timeline. Enforced server-side by role-filtered fan-out, with an asserting test.
4. **A human decides everything.** Every recommendation requires explicit executive confirmation. AI outputs and human decisions live in separate tables.
5. **Hard overrides beat weighted scores.** Confirmed D1 (immediate danger) or D2 (crisis) forces band = Critical regardless of the weighted SVI.
6. **Abstention is a valid output.** Confidence < 0.45, poor audio, or low language confidence returns `needs_human: true` and no score.
7. **AI disclosure is permanent**, and "talk to a person" is a one-tap control that transfers immediately.
8. **Nothing external is added without the user's explicit decision** (0.3).

## 0.3 External dependency protocol

Before any new package, model, dataset, API, credential, database, service, or network fetch — stop and ask:

```
EXTERNAL DEPENDENCY — decision needed
What:         <name, version>
Why:          <the task it unblocks>
Where:        <team / file>
Licence/cost: <MIT / Apache / paid / unknown>
Size/runtime: <download size, RAM, CPU vs GPU>
Demo risk:    <works offline? key needed? rate limited?>
If declined:  <the fallback I will implement>
```

Then wait. Do not install "just to test." Do not silently substitute something else for a declined dependency.

**Standing defaults:** speech (ASR/TTS), acoustics and classifiers are **self-hosted only** — victim audio never leaves the machine, which is a claim in the pitch. Telephony, SMS, WhatsApp and push notifications are **out of MVP scope**. The LLM is permitted behind an adapter with a working mock, and the system must run fully with it disabled.

## 0.4 Where to start

If the repository is empty: PART D §21, task **BE-001** (contracts) and **INF-001** (repo + Docker Compose) come first; nothing else can start without them.
If the repository exists: read `CLAUDE.md`, then the directory-level `CLAUDE.md` for whatever you are touching, then PART C for the spec of the thing you are building.

---

# PART A — PROJECT DEFINITION

## 1. Executive summary

**SAHAY-AI** is an AI-assisted intake, assessment and escalation system for the National Helpline Against Atrocities (NHAA, 14566) and the Integrated Portal of the Department of Social Justice and Empowerment.

A conversational AI assistant receives a victim's first contact by voice or text, conducts a strictly bounded intake conversation, builds a structured case profile with a **Stress Vulnerability Index (SVI)** and evidence, and escalates it to a human helpline executive who makes every decision. The victim sees a status timeline and never has to repeat their account.

**The problem it solves:** there is currently no standardised mechanism for assessing the psychological condition and vulnerability of victims at first contact. Distressed callers are triaged by whoever answers, with no consistent record of severity, no prioritisation signal, and a burden on the victim to retell traumatic events at every stage.

**What makes it defensible:** the AI is a *bounded intake instrument*, not a counsellor. Scoring is deterministic and explainable. Every output carries evidence and confidence. The system refuses to score when uncertain. A human holds all authority. Victim audio never leaves the deployment.

## 2. Problem statement (as issued)

> Design and develop an AI-enabled Real-Time Stress and Trauma Assessment Module that can assess the psychological stress, trauma, fear, anxiety, and vulnerability levels of victims/complainants interacting through NHAA (14566), the Integrated Portal, chatbot, IVRS, mobile application, or any other approved digital interface.

**Required capabilities:** analyse voice interactions, speech patterns, pauses, pitch variation, emotional indicators and textual narratives; use NLP, speech analytics and emotion AI; generate an SVI on a predefined scale; categorise into Low/Moderate/High/Critical; detect severe trauma, fear, depression, suicidal ideation, intimidation, social isolation and extreme vulnerability; automatically recommend counselling, legal aid, medical assistance, police intervention, witness protection or emergency support; support major Indian languages and dialects; maintain privacy, informed consent, confidentiality and ethical AI standards.

**Expected outcomes:** early identification of highly distressed victims; prioritisation of counselling and rehabilitation; improved victim-centric grievance redressal; better resource allocation; enhanced helpline responsiveness.

**Interpretation decisions the team has made:**

| Requirement | How it is met | Note |
|---|---|---|
| "Detect depression, suicidal ideation" | Detected as **linguistic indicators** that raise dimensions and trigger escalation | Never rendered as a diagnosis. Naming a psychiatric condition is prohibited output |
| "Automatically recommend" | Recommendations are **generated automatically and actioned only by a human** | "Automatically recommend" ≠ "automatically act" |
| "Real-time" | Sub-3-second conversational turns; assessment updates within ~8 s | Measured and reported, not asserted |
| "Major Indian languages and dialects" | Hindi + English + Hinglish in MVP; 22-language path evidenced by an IndicConformer benchmark | Each language ships only after its own evaluation |
| "IVRS, helpline" | Adapter-ready ingestion interface + documented telephony stub + full session simulation | Live integration needs departmental approval, an authorised operator and DLT registration |

## 3. Goals and non-goals

**Goals**
- G1 — Reduce the information burden on a distressed victim: they tell their account once, in their own words.
- G2 — Surface explicit safety signals (danger, crisis, coercion) within seconds, not after a queue wait.
- G3 — Give the executive a decision-ready case packet with evidence and confidence.
- G4 — Produce a consistent, explainable prioritisation signal across callers and executives.
- G5 — Keep the human unambiguously in authority, with an auditable record.
- G6 — Prove the architecture connects to real NHAA channels without redesign.

**Non-goals (state these explicitly; they are strengths, not gaps)**
- N1 — Not a diagnostic tool. It produces no clinical determination.
- N2 — Not a counsellor. It does not provide therapy, comfort strategies or emotional support techniques.
- N3 — Not an autonomous actor. It contacts no agency and closes no case.
- N4 — Not a legal adviser. It never predicts case outcomes.
- N5 — Not a replacement for a human responder. It is a first-contact structuring and triage aid.
- N6 — Not a production deployment. Live use requires clinical governance sign-off, expert weight calibration and a governed data collection process.

## 4. Stakeholders and personas

| Stakeholder | Interest |
|---|---|
| Department of Social Justice and Empowerment | Standardised vulnerability assessment; resource allocation evidence |
| NHAA 14566 operations | Faster triage; less repeated questioning; consistent records |
| State governments, UTs, district administrations | Prioritised case flow; follow-up tracking |
| Counsellors and mental-health professionals | Early identification of high-distress cases; protection from AI overreach |
| Law enforcement | Timely escalation of immediate-danger cases with evidence |
| Rehabilitation and welfare authorities | Structured need data for support allocation |

**P1 — Meena, the caller.** 34, agricultural labourer, Scheduled Caste, speaks Hindi with regional vocabulary. Owns a low-end Android phone on an unreliable network. Recently threatened after filing a complaint. May be overheard while calling. Frightened, not sure what help exists, has told her story three times already to three different people.
*Needs:* to be heard once; to know something is happening; to reach a human immediately if she wants one; to not be judged, doubted or interrogated.

**P2 — Ravi, the helpline executive.** Handles 40–60 contacts a shift. Reads fast, decides fast, is accountable for every decision. Distrusts tools that add clicks or make claims they cannot support.
*Needs:* to decide in under 90 seconds without listening to the recording; to see why the system thinks what it thinks; to override it easily and have that override recorded.

**P3 — Dr. Anjali, supervising counsellor.** Reviews escalations and audits the AI's behaviour.
*Needs:* certainty that the system never counsels, diagnoses or mishandles a crisis; visibility into disagreements between AI assessment and executive decisions.

## 5. Success metrics

| # | Metric | Target for MVP | Measured how |
|---|---|---|---|
| M1 | **Critical-event miss rate** (crisis/immediate-danger utterances not flagged) | 0 on the scripted corpus; report on held-out synthetic | Labelled corpus evaluation. **The headline safety metric** |
| M2 | Conversational turn latency (victim stops → assistant starts) | p50 < 3 s, p95 < 5 s | Instrumented turn loop |
| M3 | Time to first safety alert on the console | < 10 s from the triggering utterance | End-to-end scenario runs |
| M4 | Executive decision time on the packet | < 90 s, self-timed | Rehearsal with a non-team reader |
| M5 | Guardrail prohibition breaches under red-team | 0 reaching synthesis | Red-team log |
| M6 | ASR word error rate | Reported by language and condition, no target claimed | Common Voice Hindi + own corpus |
| M7 | Detector precision / recall / F1 | Reported per detector, recall-weighted for safety classes | Labelled corpus |
| M8 | Assessment leakage to victim client | 0 | Automated test + payload inspection |
| M9 | Repeat-question rate (assistant asking what was already answered) | < 1 per session | Scenario transcripts |

---

# PART B — PRODUCT REQUIREMENTS

## 6. Product principles

1. **The victim tells it once.** Every design decision is judged against whether it reduces retelling.
2. **The machine never decides.** It structures, flags and recommends. A human confirms.
3. **Restraint is the feature.** A bounded assistant that refuses to counsel is safer and more credible than a fluent one.
4. **Show the working.** No score without its breakdown, its evidence and its confidence.
5. **Refuse when unsure.** Abstention is a designed output, not a failure.
6. **Nothing leaves the machine.** Self-hosted speech and models are both a privacy property and a demo-reliability property.
7. **Design for the worst moment.** Assume distress, poor network, cheap phone, possibly overheard, possibly not literate in English.

## 7. Feature list

**Priority:** P0 = required for the Day 8 gate and the demo · P1 = required for a complete submission · P2 = build only if ahead of schedule.

### 7.1 Victim surfaces

| ID | Feature | Pri | Summary |
|---|---|---|---|
| VF-01 | Language selection | P0 | Hindi or English before anything else; sets session language and app locale |
| VF-02 | Consent & AI disclosure | P0 | Plain-language statement that an AI assists and a human reviews; explicit accept/decline; consent record persisted |
| VF-03 | Consent-declined mode | P1 | No AI intake, no assessment; routed straight to the executive queue; console shows analysis suppressed |
| VF-04 | Voice conversation ("Talk") | P0 | 16 kHz PCM capture, streamed; assistant audio played back; speaking indicator |
| VF-05 | Barge-in | P0 | User speech stops assistant playback immediately and becomes the next turn |
| VF-06 | Text conversation ("Chat") | P0 | Same dialogue machine over text; works when the network cannot carry audio |
| VF-07 | Talk to a person | P0 | Persistent one-tap control on every conversational screen; immediate transfer |
| VF-08 | Request timeline | P0 | Reference number + stages: received → under review → officer assigned → action taken → follow-up → closed |
| VF-09 | Add information | P1 | Append to an existing case rather than starting over — the concrete "tell it once" mechanism |
| VF-10 | Offline resilience | P1 | Audio frames and messages queue locally; flush on reconnect; calm status messaging |
| VF-11 | Whole-utterance upload fallback | P0 | Non-streaming path that always works; identical downstream pipeline |
| VF-12 | Accessibility | P1 | Large targets, high contrast, font scaling, no gesture-only actions, no English-only strings |
| VF-13 | Web portal parity | P2 | Same consent + chat flow in the browser |

### 7.2 Conversational assistant

| ID | Feature | Pri | Summary |
|---|---|---|---|
| AS-01 | Bounded dialogue state machine | P0 | 12 states, licensed questions, deterministic transitions |
| AS-02 | Free-narrative listening (S1) | P0 | Listens without probing; slots extracted, not asked |
| AS-03 | State skipping | P0 | Never asks what the narrative already answered |
| AS-04 | LLM phrasing, constrained | P0 | One sentence, chosen intent only, JSON output |
| AS-05 | Output validator | P0 | Ten prohibition checks before synthesis; failure → pre-written fallback |
| AS-06 | Per-intent fallbacks (hi/en) | P0 | System runs fully with the LLM disabled |
| AS-07 | Crisis interrupt (SX) | P0 | Unconditional; fixed script; Critical; human takeover; no resumption |
| AS-08 | Human handoff (SH) | P0 | On request or escalation; assistant muted; victim informed in their language |
| AS-09 | Endpointing & turn-taking | P0 | ~700 ms silence endpoint; no turn time limit; one gentle re-prompt after ~15 s |
| AS-10 | Language ID + lock | P1 | Detected in the first two chunks, executive-overridable |
| AS-11 | Pre-synthesised fixed turns | P0 | S0, S9, SX and all fallbacks rendered to WAV at build time |
| AS-12 | Hinglish handling | P1 | Code-switched input understood; reply matches the user's register |

### 7.3 Assessment engine

| ID | Feature | Pri | Summary |
|---|---|---|---|
| AE-01 | Acoustic feature extraction | P0 | F0 mean/variance, energy, speaking rate, pause ratio, response latency |
| AE-02 | Speech emotion (auxiliary) | P1 | One auxiliary signal feeding D4; never presented as a finding |
| AE-03 | Safety/crisis detector | P0 | High-recall lexicon (hi/en/Hinglish) + classifier; negation and quote handling |
| AE-04 | Threat & intimidation detector | P0 | Who, what, ongoing or not |
| AE-05 | Isolation / boycott / displacement detector | P1 | Feeds D6 |
| AE-06 | Medical urgency detector | P0 | Feeds D7 |
| AE-07 | Legal urgency detector | P1 | FIR status, proceedings pressure; feeds D8 |
| AE-08 | Coercion / communication-safety detector | P1 | Feeds D9; drives the neutral verification card |
| AE-09 | Structured case extraction | P0 | LLM, JSON schema: incident, timeline, persons, threats, needs, requests |
| AE-10 | SVI engine | P0 | Nine dimensions, weights, bands, hard overrides, abstention, breakdown |
| AE-11 | Uncertainty engine | P0 | ASR confidence, audio quality, language confidence, model agreement |
| AE-12 | SAFE-SIGNAL cross-modal check | P1 | Text-severity vs acoustic-distress divergence > 40 → neutral verification card |
| AE-13 | Trajectory with change-evidence | P1 | Each band change stores the utterance that caused it |
| AE-14 | Next-best-action + policy RAG | P0 | Recommendations with rationale and policy citations from pgvector |
| AE-15 | Interpretable baselines | P1 | LogReg + XGBoost for the comparison table |

### 7.4 Executive console

| ID | Feature | Pri | Summary |
|---|---|---|---|
| EC-01 | Authentication + RBAC | P0 | Executive and Supervisor roles |
| EC-02 | Live queue | P0 | Band-ranked, alerts first; language, wait time, badges, privacy-safe previews |
| EC-03 | Escalation packet view | P0 | Ten sections (PART C §14) |
| EC-04 | Two-sided transcript | P0 | Victim and assistant turns visually distinct; timestamped; original language |
| EC-05 | Evidence linking | P0 | Any assessment field → the utterances that produced it |
| EC-06 | Alerts with acknowledgement | P0 | Sorted to top; audible cue on Critical; require ack |
| EC-07 | Recommendation decisions | P0 | Confirm / modify / reject per item, with rationale; writes to `decisions_human` |
| EC-08 | Band override | P0 | Written reason mandatory, enforced server-side |
| EC-09 | Take over live session | P0 | Mutes the assistant, informs the victim, hands over the channel |
| EC-10 | Needs-Human-Assessment state | P0 | Designed state replacing the score when confidence is insufficient |
| EC-11 | Trajectory chart | P1 | Clickable, showing what moved the score |
| EC-12 | Audit viewer | P1 | Every AI output displayed, every human decision, actor and timestamp |
| EC-13 | Supervisor view | P1 | Reassignment, override review, cross-case audit, operational metrics |
| EC-14 | Case export | P2 | PDF and JSON packet |

### 7.5 Platform

| ID | Feature | Pri | Summary |
|---|---|---|---|
| PF-01 | Role-filtered event fan-out | P0 | Server-side; victim tokens cannot receive assessment events |
| PF-02 | Turn orchestration | P0 | Reply path fast; assessment path queued and parallel |
| PF-03 | Audit logging | P0 | AI display events and human decisions, separately, immutable |
| PF-04 | Encrypted audio storage + retention | P1 | Shorter retention than derived case data |
| PF-05 | Adapter pattern + mocks | P0 | Every external provider behind an interface with a mock |
| PF-06 | Telephony adapter stub | P0 | Documented, unimplemented; judge-facing evidence |
| PF-07 | Latency instrumentation | P1 | Per-stage timings persisted for the evaluation table |
| PF-08 | One-command local run | P0 | `docker compose up` with no external service |

## 8. Detailed specifications for the complex features

### 8.1 VF-02 Consent and AI disclosure

**User story.** As a distressed caller, I need to know that I am talking to a machine, that a person will read this, and that I can reach a person now, before I say anything private.

**Acceptance criteria**
- Shown before any capture begins; no audio or text is transmitted before a decision.
- States in the selected language: an AI assistant will talk with you first; a helpline officer will review everything you say; you can ask for a person at any time.
- Two explicit actions: accept, decline. No default selection, no dark pattern, no pre-ticked box.
- On accept: `consents` row written with `{given: true, ts, channel, lang, script_version, session_id}`.
- On decline: session continues in **VF-03** mode — no AI intake, no assessment, routed to the queue.
- The disclosure remains visible in the interface for the whole session, not only at the start.

### 8.2 AS-01/04/05 The bounded dialogue loop

**Sequence for one turn**
1. VAD detects endpoint after ~700 ms silence.
2. ASR produces the final transcript for that utterance.
3. **Safety pre-check** on the utterance (lexicon + crisis classifier). If fired → SX, stop here.
4. **Dialogue policy** (`dialogue.next`) selects exactly one approved intent from the current state and filled slots.
5. **LLM phrasing** renders that intent as one sentence in the session language, given the intent, slots and last two turns. Output is JSON `{"text": "..."}`.
6. **Validator** (`guardrails.validate`) applies ten checks. On failure → the intent's pre-written fallback.
7. **TTS** streams audio (or plays the pre-synthesised WAV for a fixed turn).

**Acceptance criteria**
- The LLM cannot change state, add a question, or introduce content outside the intent.
- Every intent has hi and en fallback text; with `LLM_PROVIDER=mock` a complete session runs on fallbacks.
- Turn latency p50 < 3 s measured end to end.
- Repeat-question rate < 1 per session on the scripted corpus (states skip when slots are filled).
- Barge-in cancels playback within 200 ms of local VAD detection.

### 8.3 AS-07 Crisis interrupt

**User story.** As a caller expressing suicidal intent, I must not be kept talking to a machine.

**Acceptance criteria**
- Detection runs before the dialogue policy on every utterance, in Hindi, English and Hinglish, tuned for **recall over precision**.
- Transition to SX is unconditional in code — not a model output, not a threshold on the full assessment pipeline.
- A fixed, pre-approved, pre-synthesised script plays: acknowledges, states plainly that a person will speak with them now, asks them to stay. No advice, no questions, no assessment.
- Band forced to Critical; alert raised with `requires_ack: true`; case moved to the top of the queue with an audible cue.
- Intake does not resume. Only a human takeover continues the session.
- **The SX script must be reviewed by a counsellor or psychology faculty member before Day 8**, and that review named in the deck.
- Test: the scripted crisis line triggers all of the above, asserted automatically.

### 8.4 AE-10 SVI engine

Full specification in PART C §13. Acceptance criteria:
- Pure function: no I/O, no network, no model loading, standard library only.
- Returns `{svi, band, needs_human, breakdown, overrides_applied}`.
- Hard overrides fire regardless of the weighted sum; `overrides_applied` explains the band.
- Confidence < 0.45 or poor quality → `needs_human: true`, **no score emitted**.
- Text-only sessions: D4 not applicable, remaining weights renormalise — explicitly tested.
- Unit tests cover: weight arithmetic, each band boundary, each override, each abstention path, missing-modality renormalisation.

### 8.5 EC-03 Escalation packet

**User story.** As an executive, I need to decide in under 90 seconds without listening to the recording.

**Ten sections** (details in PART C §14): header, assessment summary, safety alerts, structured case record, full two-sided transcript, evidence panel, trajectory, recommended pathways, uncertainty block, decision area.

**Acceptance criteria**
- Band and reference visible without scrolling.
- SVI never displayed without its breakdown and confidence adjacent.
- Every structured field links to its source utterance.
- Recommendations render as *awaiting decision*; no state renders as "action taken" before confirmation.
- Alerts sort above everything and require acknowledgement.
- The disclaimer line is on the screen: *"This assessment is an assistive prioritisation aid generated by an AI system. It is not a clinical, legal or forensic determination. All decisions rest with the reviewing officer."*
- Timed test: a reader outside the team decides in under 90 seconds.

### 8.6 VF-08 Victim timeline

**Acceptance criteria**
- Stages: request received → under review → officer assigned → action taken → follow-up scheduled → closed/continuing.
- Contains **no** assessment field. Verified by inspecting the API payload, not the UI.
- Shows only executive-confirmed actions. A recommendation is not an action.
- Plain language: "a counsellor will call you", never "counselling pathway initiated".
- Automated test asserts the timeline response contains none of: `svi`, `band`, `dimension`, `alert`, `confidence`.

## 9. Explicitly out of scope for the MVP

Telephony/IVRS integration · SMS, WhatsApp, Telegram · push notifications · languages beyond Hindi and English · full-duplex low-latency voice · production authentication (SSO, MFA) · multi-tenant district deployment · real victim data of any kind · mobile app store distribution · the multimodal SAFE-SIGNAL model (rule-based only in MVP).

---

# PART C — TECHNICAL SPECIFICATION

## 10. Architecture

```
VICTIM SURFACES (React Native app · web portal)
  language → consent → Talk / Chat → timeline
  persistent "Talk to a person" · NEVER shows assessment
        │ WSS: ▲ assistant TTS audio  ▼ victim PCM audio + chat JSON
SESSION GATEWAY (FastAPI)
  auth · consent gate · turn orchestration · role-filtered fan-out
  adapters/telephony_adapter.py ← documented stub
        ├─ REPLY PATH (fast, synchronous)
        │    VAD → ASR → SAFETY PRE-CHECK → DIALOGUE POLICY →
        │    LLM PHRASING → VALIDATOR → TTS → assistant audio
        │    (crisis pre-check → fixed script + human takeover)
        └─ ASSESSMENT PATH (queued, parallel, never blocks the reply)
             acoustics · SER · MuRIL distress+crisis · threat · isolation ·
             medical · legal · coercion · LLM structured extraction
                   ↓
             VULNERABILITY ENGINE  D1..D9 → SVI → band
             uncertainty · hard overrides · SAFE-SIGNAL · trajectory
                   ↓
             NEXT-BEST-ACTION + POLICY RAG (pgvector, cited)
                   ↓
             ESCALATION PACKET → EXECUTIVE CONSOLE (the deciding authority)
                   ↓ decision events
             VICTIM TIMELINE (status only)
```

**Non-obvious design decisions and their reasons**

| Decision | Reason |
|---|---|
| No WebRTC | Topology is client-to-server, not peer-to-peer. WebRTC would add signalling, ICE, STUN/TURN and a media server to solve a problem that does not exist here |
| Reply and assessment paths separated | If SVI computation is on the reply path, the assistant hesitates for seconds at emotionally critical moments |
| Deterministic FSM, LLM phrases only | A free-form LLM talking to trauma victims is indefensible and a mental-health panel will say so within thirty seconds |
| Fixed turns pre-synthesised | Removes TTS from the critical path for ~half of turns; makes the crisis script instantaneous |
| Self-hosted speech | Privacy claim + demo reliability + no data-residency question |
| Pure modules for dialogue/guardrails/SVI | Backend integrates them with zero ML dependencies; CI tests them in seconds |
| Role filtering server-side | A client-side filter is one bug away from telling a distressed woman a machine rated her Critical |

## 11. Data model

```sql
users(id, username, password_hash, role /* executive|supervisor */, display_name,
      created_at)

sessions(id, case_id, channel /* mobile_voice|mobile_chat|portal_chat|upload */,
         lang, state, consent_id, started_at, ended_at, human_joined_at,
         audio_quality, asr_conf_avg)

consents(id, session_id, given, ts, channel, lang, script_version, captured_by)

turns(id, session_id, turn_index, speaker /* victim|assistant|officer */,
      text, lang, t_start_ms, t_end_ms, asr_conf, intent /* assistant only */,
      state /* FSM state at this turn */, audio_path, created_at)

cases(id, reference_no, session_id, status, band, svi, needs_human,
      assigned_officer_id, created_at, updated_at)

assessments(id, case_id, cycle_index, svi, band, needs_human,
            dims_json /* D1..D9: {score, conf, evidence_turn_ids[]} */,
            overrides_applied_json, confidence_agg, quality_json,
            scoring_version, normalization_json /* PC-08 */, created_at)

alerts(id, case_id, type /* crisis|threat|medical|coercion */, severity,
       evidence_turn_ids_json, requires_ack, acked_by, acked_at, created_at)

recommendations(id, case_id, action_type /* counselling|legal_aid|medical|
                police|witness_protection|welfare|follow_up */,
                rationale, policy_citations_json, confidence, created_at)

decisions_ai(id, case_id, recommendation_id, produced_at, model_version,
             payload_json)          -- what the AI proposed

decisions_human(id, case_id, recommendation_id, officer_id,
                decision /* confirm|modify|reject */, rationale,
                decided_at)          -- what the human decided. SEPARATE TABLE.

overrides(id, case_id, officer_id, from_band, to_band, reason /* REQUIRED */,
          created_at)

timeline_events(id, case_id, stage, label, ts)   -- victim-safe only; authoritative timeline

audit_log(id, case_id, actor_type /* system|human */, actor_id, event,
          detail_json, ts)           -- append-only; nobody may delete

policy_chunks(id, source, citation, text, embedding vector(768))

latency_metrics(id, session_id, turn_index, stage, ms, created_at)
```

**Invariants:** `decisions_ai` and `decisions_human` are never joined into one table or one view that hides which is which. `audit_log` is append-only. `overrides.reason` is `NOT NULL` and enforced at the endpoint.

**Lead decisions of 2026-09-11 (`docs/contracts/PROPOSED_CHANGES.md`).**

- **PC-03.** `overrides` and `timeline_events` are the authoritative stores for band overrides and victim-safe stages. `audit_log` also records each write for accountability, but it is not the timeline. The local build has 15 tables: the 15 above, with `policy_chunks` using keyword retrieval instead of an embedding column.
- **PC-07.** An officer turn (`speaker = officer`) exists only after takeover, when `sessions.human_joined_at` is set.
- **PC-08.** `assessments.scoring_version` and `assessments.normalization` record how each score was produced.
- **PC-10.** Enumerations are frozen in `docs/contracts/CONTRACTS.md` section 9.

## 12. API specification

### 12.1 Transport
```
WSS /ws/session/{session_id}                       (PC-05 target: first frame {"type":"auth","token":...})
WSS /ws/session/{session_id}?token=<jwt>           (transitional, text-first web slice only)
UP    binary  16 kHz mono PCM16 · 500 ms frames · 8-byte header (uint32 seq | uint32 ms)
      text    {"type":"chat.message","text":...,"lang":...}
              {"type":"request_human"}
DOWN  binary  assistant TTS chunks, prefixed with turn_id header
      text    events (12.2, 12.3)
FALLBACK      POST /sessions/{id}/audio  — whole-utterance upload, always available
RECONNECT     client resumes from last acknowledged seq; server de-duplicates
```
**PC-05, approved in principle and phased.** The target is:
- no JWT in the socket URL;
- an auth frame sent immediately after connecting;
- no session or assessment data before authentication succeeds;
- a short authentication timeout;
- an invalid or expired token closes the connection;
- tokens are never logged.

The query-token form stays temporarily for the text-first web slice. Backend and Executive Web own the implementation. See CONTRACTS.md section 1.

### 12.2 Events — victim client MAY receive
```
assistant.turn   {turn_id, text, lang, intent, audio:"streaming"|"prerecorded"}
transcript.line  {turn_id, speaker:"victim"|"assistant", text, lang, ts}
session.status   {state, consent, lang, human_joined}
timeline.update  {stage, label, ts}
officer.message  {turn_id, text, lang, ts, origin:"human_officer"}   (PC-07, only after takeover)
```

### 12.3 Events — EXECUTIVE CONSOLE ONLY (server-enforced by role)
```
dimension.update   {dims:{D1..D9:{score, conf, evidence_turn_ids[]}},
                    svi, band, needs_human, overrides_applied[]}
alert.safety       {alert_type, severity, evidence_turn_ids[], requires_ack:true}   (PC-02)
case.structured    {incident, timeline[], persons[], threats[], safety_now,
                    medical_need, legal_status, isolation, requested_support}
action.recommended {action_id, action_type, rationale, policy_citations[], confidence}
safesignal.flag    {direction, delta, suggested_question}
escalation.packet  {case_id, band, alerts[], summary, ready:true}
```

### 12.4 REST
```
POST /auth/login                → {token, role, display_name}
POST /sessions                  {channel, consent, lang} → {session_id, case_id, reference_no,
                                  session_token, ws_url, lang, consent, ai_disclosure,
                                  human_request_available}          (PC-09; ws_url has no token)
POST /sessions/{id}/audio       whole-utterance fallback
POST /sessions/{id}/end         → {case_id, reference_no}
GET  /queue                     → band-ranked case summaries
GET  /cases/{id}                → full escalation packet
POST /cases/{id}/claim
POST /cases/{id}/decisions      {action_id, decision, rationale, officer_id}
POST /cases/{id}/override       {band, reason}     # reason REQUIRED (400 if absent)
POST /cases/{id}/takeover
POST /cases/{id}/alerts/{alert_id}/ack   → {alert_id, case_id, acknowledged_by, acknowledged_at}  (PC-01)
POST /cases/{id}/messages       {text, lang?}  officer text after takeover only (PC-07)
GET  /cases/{id}/timeline       victim-safe view — must contain no assessment field
GET  /cases/{id}/audit
```
Console writes are executive-only. The supervisor view is read-only until PC-06 is taken up. Queue push (PC-04) is deferred and the console polls `/queue`. The frozen shapes are in CONTRACTS.md sections 4 and 9.

### 12.5 Pure module interfaces
```python
dialogue.next(state, slots, utterance, safety_flags)
    -> {next_state, intent, licensed_question, fallback_text}
guardrails.validate(text, intent, lang)
    -> {ok: bool, reason: str, safe_text: str}
svi.compute(dimension_scores, confidences, quality)
    -> {svi, band, needs_human, breakdown, overrides_applied}
```
No I/O, no network, no model loading. This is a deliberate architectural property — protect it.

## 13. SVI specification

| Dim | Meaning | Weight |
|---|---|---|
| D1 | Immediate safety threat | 0.22 |
| D2 | Crisis / self-harm language | 0.18 |
| D3 | Fear, intimidation, threats | 0.13 |
| D4 | Acute distress (acoustic + emotional) | 0.12 |
| D5 | Trauma-associated indicators | 0.08 |
| D6 | Social isolation, boycott, displacement | 0.08 |
| D7 | Medical urgency | 0.08 |
| D8 | Legal urgency | 0.06 |
| D9 | Communication safety (cannot speak freely) | 0.05 |

`SVI = Σ(weight_i × score_i)`, each score 0–100.
**Bands:** 0–29 Low · 30–54 Moderate · 55–74 High · 75–100 Critical.

**Renormalisation (PC-08).** Weights are rescaled only for a dimension that is *structurally* unavailable on the channel: D4 on a typed channel.

`normalized_svi = weighted_sum_available / sum_of_available_weights`. With only D4 absent the denominator is 0.88.

- The scoring version, available and unavailable dimensions, and normalisation factor are stored with every assessment.
- D4 is shown as unavailable, never measured and never zero.
- Poor audio, runtime failure or low confidence never rescale; they abstain.
- Hard overrides apply independently. Band thresholds apply to the normalised value, using lower bounds 0/30/55/75.

**Hard overrides:** confirmed D1 or D2 above threshold ⇒ Critical regardless of the weighted sum. Confidence < 0.45, poor audio quality, or low language confidence ⇒ `needs_human: true`, no score. Consent declined ⇒ scoring suppressed entirely.

**Presentation contract:** never a bare number; breakdown and confidence always adjacent; every dimension carries its evidence turn ids; weights labelled in the UI as *provisional, pending expert calibration*.

**SAFE-SIGNAL:** compute text-content severity and acoustic-distress independently; divergence > 40 points either way raises a neutral cross-modal card. It never characterises the caller as deceptive; it suggests one non-leading verification question (e.g. whether they are somewhere they can speak freely).

## 14. Escalation packet specification

| Section | Contents | Rule |
|---|---|---|
| Header | Reference, language, channel, duration, consent status, band | Visible without scrolling |
| Assessment | SVI, nine-dimension breakdown, aggregate confidence, overrides applied | Never a bare number |
| Alerts | Type, severity, triggering utterance | Top of the packet; require acknowledgement |
| Structured case | Incident, timeline, persons, threats, safety now, medical, legal, isolation, stated request | Every field links to its source utterance |
| Transcript | Both sides, timestamped, original language | Assistant turns visually distinct |
| Evidence | Dimension → utterances | No assessment without traceable evidence |
| Trajectory | SVI over time with the utterance that moved it | Clickable |
| Recommendations | Pathway, rationale, policy citation, confidence | Rendered as awaiting decision |
| Uncertainty | ASR confidence, audio quality, language confidence, model agreement — or Needs-Human-Assessment | Equal prominence to the score |
| Decision area | Confirm/modify/reject each, band override with mandatory reason, takeover | Writes to `decisions_human` |

## 15. Dialogue specification

| State | Purpose | Licensed question | Slots |
|---|---|---|---|
| S0 OPENING | Fixed, pre-recorded. AI disclosure, human-review statement, right to a human, invitation to speak | — | — |
| S1 FREE NARRATIVE | Listen; acknowledge neutrally; do not probe | none | incident, persons, location, time (extracted) |
| S2 IMMEDIATE SAFETY | The most important question | Are you safe right now — can the person who harmed you reach you? | safety_now, proximity_of_threat |
| S3 MEDICAL NEED | Never asks injury detail | Does anyone need medical help right now? | medical_need, urgency |
| S4 WHO AND WHEN | Gap-fill; **skipped if answered** | who / when | persons, relationship, when, where |
| S5 ONGOING THREAT | Continuing pressure, witness risk | Are threats continuing — has anyone told you not to complain? | threat_ongoing, intimidation, witness_concern |
| S6 SUPPORT NETWORK | Isolation, boycott, displacement | Is there someone with you right now? | isolation, displacement, support_person |
| S7 EXISTING ACTION | Case status | Has a complaint or FIR been filed — do you have legal help? | fir_status, legal_help |
| S8 WHAT THEY WANT | Stated need is first-class | What help are you looking for right now? | requested_support |
| S9 CLOSING | Fixed, pre-recorded. Recording confirmed, reference number, what happens next. **No outcome promises** | — | — |
| SX CRISIS INTERRUPT | From any state, unconditional. Fixed script, Critical, human takeover, no resumption | — | — |
| SH HUMAN HANDOFF | From any state on request or escalation | — | — |

Target 8–12 turns. The chat channel uses the identical machine. Only SX may interrupt, and only from the fast safety pre-check.

## 16. Guardrail specification

**Input side — safety pre-check.** High-recall lexicons (hi/en/Hinglish) + crisis classifier, on every utterance before the dialogue policy. Recall prioritised: a false alarm costs an executive thirty seconds; a miss costs far more.

**Output side — validator.** Ten checks before synthesis:

| Check | Fails if the sentence |
|---|---|
| Length | is more than one sentence or over the word limit |
| Unlicensed question | asks anything the current intent does not license |
| Advice | matches advice patterns (you should, you must, try to, file a…) |
| Promise | promises outcome, timeline, arrest, protection, compensation |
| Diagnosis | names a psychological state as fact (depression, trauma, PTSD, disorder) |
| Banned comfort | matches the minimising-phrase list in either language |
| Detail-seeking | probes an assault, injury or death |
| Blame | doubts, tests or blames the account; asks a victim "why" |
| Language | does not match the session language |
| Disclosure | claims or implies the assistant is human |

Failure ⇒ speak the pre-written fallback and log the rejection with intent and rejected text. Rejection rate is a tracked metric.

**Red-team requirement.** Systematically attempt to induce every prohibition — adversarial phrasings, code-switching, quoted speech, hypotheticals, roleplay framings, instructions embedded in the victim's own words. Log attempt, output and whether the validator caught it. A red-team report with zero failures means the red-team was not trying.

## 17. Non-functional requirements

| Area | Requirement |
|---|---|
| **Latency** | Turn p50 < 3 s, p95 < 5 s. Assessment update ≤ 8 s after each cycle. Packet ready ≤ 15 s after session end |
| **Availability** | Whole system runs on one machine via `docker compose up`, fully offline except the LLM, which has a mock |
| **Privacy** | Consent before capture; audio never leaves the deployment; encrypted audio volume; audio retention shorter than derived case data; data minimisation in queue previews |
| **Security** | JWT + RBAC; role-filtered socket fan-out; secrets via env only; no keys in the repository; rate limiting; CORS restricted |
| **Auditability** | Every AI output displayed and every human decision logged with actor and timestamp; append-only; AI and human records separate |
| **Accessibility** | Large targets, high contrast, font scaling, no gesture-only actions, no English-only strings, chat available when audio is not |
| **i18n** | Every victim-facing string in `hi.json`/`en.json`; Hinglish input supported; original-language transcript always preserved |
| **Resilience** | Whole-utterance upload fallback; offline queue with resume; pre-synthesised fixed turns; mock LLM adapter |
| **Legal framing** | DPDP Act 2023 alignment documented; no claim of clinical validity; provisional weights labelled in-product |

## 18. Technology stack

| Layer | Choice | Rationale |
|---|---|---|
| Mobile | React Native + Expo **development build** | Shares types with the console; dev build required for raw mic access |
| Audio capture | 16 kHz mono PCM16, 500 ms frames | Whisper's native format; small frames for endpointing latency |
| Transport | One WebSocket, binary both ways + JSON | No WebRTC needed for client-to-server |
| Console | React 18 + TS + Vite + Tailwind + shadcn/ui + Recharts | Fast to build, sober defaults |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2 | Pydantic models are the contract |
| Queue | Redis 7 + RQ | Simpler to operate than Celery for a short sprint |
| DB | PostgreSQL 16 + pgvector | Cases and policy retrieval in one auditable store |
| ASR | faster-whisper small, int8, CPU | Near-real-time on CPU; handles Hinglish; self-hosted |
| VAD | silero-vad | Drives endpointing; biggest lever on perceived responsiveness |
| TTS | Piper (latency) / AI4Bharat Indic Parler-TTS (quality); fixed turns pre-synthesised | Self-hosted |
| NLP | MuRIL / IndicBERT v2; XLM-R fallback | Code-switch tolerant; the local, inspectable layer |
| LLM | Claude API behind `llm_adapter.py` with mock; JSON-schema outputs | Phrasing, extraction, summary only |
| Benchmark | AI4Bharat IndicConformer-600M (MIT, 22 languages) | Evidence for the multilingual roadmap |
| Baselines | LogReg + XGBoost | Required comparison |
| Infra | Docker Compose, GitHub Actions, single VM or laptop | One-command start |

---

# PART D — IMPLEMENTATION PLAN

## 19. Repository structure

```
sahay-ai/
├── CLAUDE.md                  master instructions (governs everything)
├── CONTRIBUTING.md            git workflow
├── ml/                        Team A   dialogue · guardrails · svi · asr · tts ·
│                                       acoustics · nlp · eval · tests
├── backend/                   Team B   app/{models,schemas,api,ws,workers,
│                                       adapters,services,core} · tests
├── frontend/                  Team C   executive console
├── mobile/                    Team C   victim app
├── data-scripts/                       corpus tooling (scripts only, never audio)
├── infra/                              docker-compose, deploy
├── docs/
│   ├── contracts/CONTRACTS.md          frozen interfaces
│   ├── dialogue/STATES.md              states + fixed scripts
│   └── plan/PHASES.md                  14-day plan and gates
└── .claude/                   commands · agents · skills · templates
```

## 20. Phases and gates

| Phase | Days | Ends when |
|---|---|---|
| P0 Contracts & skeleton | 1 | Contracts committed; repo protected; React↔FastAPI WebSocket message; **Expo dev build on a physical phone** |
| P1 The conversation exists | 2–4 | **GATE:** a person speaks Hindi to the phone and the assistant answers out loud, correctly, in ~3 s, driven by the FSM |
| P2 Assessment & escalation | 5–8 | **GATE:** consent → conversation → live assessment → crisis interrupt → Critical alert → executive decides → takeover → timeline updates; role fan-out holds; LLM-off session completes |
| P3 Hardening & evaluation | 9–11 | Latency measured, red-team table done, all 10 scenarios pass in hi/en/Hinglish, clean and noisy |
| P4 Freeze & demo | 12–13 | `v0.9-freeze` tagged; backup video; APK tested on an outside phone; deck and tables done |
| P5 Buffer | 14 | `v1.0-demo` tagged; rehearsed from that tag |

**Gates are dates.** A failed gate cuts scope; it never extends the phase.
**Cut list, in order:** optional push-to-talk → supervisor view → case export → trajectory interactivity → web portal parity → second language → native app (fall back to mobile web).
**Never cut:** evaluation, crisis interrupt, role-filtered fan-out, consent flow, human decision step.

## 21. Task backlog

Format: `ID · task · owner · depends on · phase`. P0 features first.

### Backend (B)
| ID | Task | Owner | Depends | Phase |
|---|---|---|---|---|
| BE-001 | Freeze and commit `docs/contracts/CONTRACTS.md` | B1 | — | P0 |
| INF-001 | Monorepo, Docker Compose (api, worker, redis, postgres, frontend), CI, branch protection | B4 | — | P0 |
| BE-002 | DB schema v1 + Alembic migrations (§11) | B1 | BE-001 | P0 |
| BE-003 | Auth + RBAC (executive, supervisor) | B1 | BE-002 | P1 |
| BE-004 | `POST /sessions`, consent capture + consent gate | B1 | BE-002 | P1 |
| BE-005 | WebSocket server: binary up, binary down, JSON both ways | B2 | BE-001 | P1 |
| BE-006 | **Role-filtered fan-out + `test_role_fanout.py`** (write the test first) | B2 | BE-005 | P1 |
| BE-007 | Turn orchestrator wired to `ml.dialogue` (reply path only) | B2 | BE-005, AI-002 | P1 |
| BE-008 | Encrypted audio storage + whole-utterance upload fallback | B2 | BE-004 | P1 |
| BE-009 | `adapters/base.py`, `llm_adapter.py` + mock, `telephony_adapter.py` stub | B3 | INF-001 | P1 |
| BE-010 | Redis + RQ workers; assessment jobs off the reply path | B3 | BE-002 | P2 |
| BE-011 | Persist turns, assessments, alerts, recommendations | B1 | BE-002, BE-010 | P2 |
| BE-012 | Crisis path prioritised over normal turn flow | B2 | BE-007, AI-005 | P2 |
| BE-013 | Escalation packet assembly service | B1 | BE-011 | P2 |
| BE-014 | `claim` / `decisions` / `override` (reason enforced) / `takeover` endpoints | B1 | BE-013 | P2 |
| BE-015 | Audit middleware: log AI displays and human decisions separately | B1 | BE-014 | P2 |
| BE-016 | Policy RAG corpus into pgvector + cited retrieval | B3 | BE-002 | P2 |
| BE-017 | Next-best-action endpoint | B3 | BE-016 | P2 |
| BE-018 | Victim timeline endpoint + leakage test | B1 | BE-013 | P2 |
| BE-019 | Latency instrumentation across all turn stages | B2 | BE-007 | P3 |
| BE-020 | Reconnection + resume; three-session load test | B2 | BE-005 | P3 |
| BE-021 | Supervisor endpoints; case export | B1 | BE-014 | P3 |
| INF-002 | Deploy to the demo machine; backup/restore; security checklist | B4 | INF-001 | P3 |

### AI/ML (A)
| ID | Task | Owner | Depends | Phase |
|---|---|---|---|---|
| AI-001 | SVI engine (pure) + full unit tests — spec is complete, no research needed | A4 | BE-001 | P0 |
| AI-002 | Dialogue FSM: 12 states, intents, transitions, slot skipping (pure) + tests | A2 | BE-001 | P1 |
| AI-003 | **Fixed scripts S0/S9/SX in hi+en, reviewed, pre-synthesised — DUE END OF DAY 3, BLOCKS B AND C** | A2 | — | P1 |
| AI-004 | Guardrail lexicons (hi/en/Hinglish) + output validator + tests | A2/A3 | — | P1 |
| AI-005 | Crisis pre-check: lexicon + classifier, recall-tuned | A3 | AI-004 | P1 |
| AI-006 | ASR: faster-whisper endpointed per utterance; silero VAD tuning | A1 | — | P1 |
| AI-007 | TTS: Piper pipeline; pre-synthesis build step | A1 | AI-003 | P1 |
| AI-008 | **Ten two-sided scenario scripts recorded (hi/en, quiet/noisy) — DUE END OF DAY 4** | A4 | — | P1 |
| AI-009 | Synthetic text corpus (1.5–3k, human-reviewed) | A3 | — | P2 |
| AI-010 | LLM phrasing prompt + per-intent fallbacks | A4 | AI-002, AI-004 | P2 |
| AI-011 | LLM structured extraction (JSON schema) | A4 | — | P2 |
| AI-012 | MuRIL distress + crisis classifiers | A3 | AI-009 | P2 |
| AI-013 | Threat, isolation, medical, legal, coercion detectors | A3 | AI-004 | P2 |
| AI-014 | Acoustic features + audio-quality score + D4 scorer | A2 | — | P2 |
| AI-015 | SER model (auxiliary) fine-tuned on RAVDESS+CREMA-D | A2 | — | P2 |
| AI-016 | Uncertainty engine (ASR conf, quality, language, agreement) | A4 | AI-001 | P2 |
| AI-017 | Interpretable baselines (LogReg, XGBoost) | A3 | AI-009 | P2 |
| AI-018 | SAFE-SIGNAL divergence rule + thresholds | A2 | AI-014 | P3 |
| AI-019 | Full evaluation: WER, P/R/F1, critical-miss, calibration, fairness, ablations | A1/A3 | AI-008 | P3 |
| AI-020 | Guardrail red-team + table | A2 | AI-004 | P3 |
| AI-021 | LLM offline cache; judge-defence document | A4 | AI-010 | P3 |

### Frontend & Mobile (C)
| ID | Task | Owner | Depends | Phase |
|---|---|---|---|---|
| FE-001 | **Expo development build on a physical phone with mic + speaker** — highest-uncertainty task, two people, Day 1 | C1+C2 | — | P0 |
| FE-002 | Console scaffold: Vite, React, TS, Tailwind, routing, WS client | C3 | — | P0 |
| FE-003 | Mobile: Language, Consent (AI disclosure), Home screens | C2 | FE-001 | P1 |
| FE-004 | Mobile: 16 kHz PCM capture; whole-utterance upload path first | C1 | FE-001 | P1 |
| FE-005 | Mobile: TTS playback queue + barge-in on local VAD | C1 | FE-004 | P1 |
| FE-006 | Mobile: chat screen; hi/en strings complete | C2 | FE-003 | P1 |
| FE-007 | Mobile: persistent "Talk to a person" control | C2 | FE-003 | P1 |
| FE-008 | Console: login, queue on mock data | C4 | FE-002 | P1 |
| FE-009 | Console: three-region case layout + two-sided transcript with span highlighting | C3 | FE-002 | P1 |
| FE-010 | Mobile: streaming both ways, reconnection, offline queue | C1 | FE-005, BE-005 | P2 |
| FE-011 | Console: real events; structured record with evidence links | C3 | BE-011 | P2 |
| FE-012 | Console: SVI gauge, dimension breakdown, confidence chips, Needs-Human state | C3 | BE-011 | P2 |
| FE-013 | Console: alert banners with acknowledgement + audible cue | C4 | BE-011 | P2 |
| FE-014 | Console: recommendation cards (confirm/modify/reject) + override with reason | C4 | BE-014 | P2 |
| FE-015 | Console: takeover button | C3 | BE-014 | P2 |
| FE-016 | Mobile: consent-declined mode; takeover notification; MyRequests timeline | C2 | BE-018 | P2 |
| FE-017 | Console: trajectory chart with clickable evidence | C3 | BE-011 | P3 |
| FE-018 | Console: SAFE-SIGNAL and coercion cards | C3 | AI-018 | P3 |
| FE-019 | Console: supervisor view, audit viewer, case export UI | C4 | BE-021 | P3 |
| FE-020 | Mobile: APK build; permissions, battery, accessibility, error/offline states | C1/C2 | FE-010 | P3 |

### PM
| ID | Task | Phase |
|---|---|---|
| PM-001 | Run Day 1 all-hands: freeze contracts, schema, SVI, dialogue states | P0 |
| PM-002 | Seed the board: every P0/P1 task as an issue, labelled and assigned | P0 |
| PM-003 | Run integration checkpoints twice daily from Day 5 | P2+ |
| PM-004 | Arrange counsellor review of the SX script before Day 8 | P2 |
| PM-005 | Deck, ethics one-pager, architecture poster, judge Q&A | P4 |
| PM-006 | Backup video; rehearse the 90-second script ≥5 times with a substitute driver | P4 |

## 22. Definition of done

A task is done when: merged into `dev` with CI green and one approval from a different team (two for `type:dialogue`); works from a clean clone via `docker compose up`; contracts or dialogue docs updated in the same PR if touched; external calls sit behind an adapter with a mock; anything user-facing has been seen on a real phone or a second machine.

## 23. Testing strategy

| Level | What | Where |
|---|---|---|
| Unit — pure modules | Dialogue transitions, state skipping, crisis interrupt; every guardrail prohibition in both languages; SVI weights, bands, each override, abstention, renormalisation | `ml/tests/` — must run in seconds, no ML deps |
| Unit — backend | Consent gate; override reason enforcement; AI/human decision separation | `backend/tests/` |
| **Safety invariant tests** | `test_role_fanout.py` (victim token cannot receive `dimension.update`); timeline payload contains no assessment field; crisis line forces SX + Critical; mobile source contains no `svi`/`band`/`dimension` | Never skipped, never deleted |
| Integration | Full session: consent → conversation → assessment → escalation → decision → timeline | Scenario runner |
| Scenario | Ten scripted scenarios × {hi, en, Hinglish} × {quiet, noisy} | `ml/eval/` |
| Non-functional | Turn latency distribution; three concurrent sessions; reconnection; LLM-off mode | `backend/tests/` + manual |
| Adversarial | Guardrail red-team (§16) | `ml/eval/redteam/` |

## 24. Evaluation plan

| Metric | Applied to | Why |
|---|---|---|
| WER / CER | ASR, per language, clean vs noisy | Everything downstream depends on transcript quality |
| Precision / recall / F1 | Each detector | Standard quality, recall-weighted for safety classes |
| **Critical-event miss rate** | Crisis and immediate-danger detection | The headline safety metric — the failure that harms someone |
| AUPRC | Rare high-severity classes | More informative than accuracy under imbalance |
| Calibration | Dimension confidences, SVI | Justifies the 0.45 abstention threshold |
| Latency distribution | Every turn stage | Substantiates the real-time claim |
| Per-language / per-condition slices | hi, en, Hinglish; clean, noisy | Fairness evidence |
| Ablation | text-only / voice-only / both / full | Converts the USP into a measured result |
| Baseline comparison | LogReg, XGBoost vs the stack | Evidence the architecture earns its complexity |
| Inter-annotator agreement | Team-labelled corpora | Establishes the labels are trustworthy |
| Guardrail red-team | Assistant output | Establishes the prohibitions hold under pressure |

## 25. Data strategy

| Corpus | Purpose | Status |
|---|---|---|
| RAVDESS, CREMA-D | SER baseline (English, acted) | Open |
| Common Voice Hindi, Kathbath, MUCS, GramVaani | ASR evaluation, noise robustness | Open |
| Dreaddit, GoEmotions | English text distress baseline | Open |
| IEMOCAP, DAIC-WOZ | Research context | Licence request — days to weeks; never on the critical path |
| **Own scripted scenario corpus** | Demo + workflow evaluation | Team-recorded, due Day 4. **Highest-risk deliverable** |
| **Synthetic labelled text** | Classifier training | LLM-generated, human-reviewed |

**Honesty framing:** public corpora establish capability, not clinical validity. Scripted and synthetic corpora validate the workflow, not the population. Real NHAA data is a future, governed activity only — consented, de-identified, expert-annotated, access-controlled. Say this before being asked; volunteering it converts a weakness into credibility.

**Annotation rule:** annotate at evidence level, never diagnosis level. High-consequence labels double-annotated with third-person adjudication. Never annotate a psychiatric diagnosis.

## 26. Git workflow

```bash
git checkout dev && git pull
git checkout -b <type>/<team>-<description>     # feat/ai-svi-engine
git push -u origin <branch>                     # DRAFT PR immediately
# work, commit small: feat(svi): add hard override rule for crisis signals
<run tests>
git fetch origin && git rebase origin/dev
git push --force-with-lease                     # mark Ready for review
# 1 approval from ANOTHER team + green CI → Squash and merge → delete branch
```
Types `feat fix chore docs test refactor` · teams `ai be fe infra`.
Tags: `v0.1-day4`, `v0.2-day8`, `v0.9-freeze`, `v1.0-demo`. `dev`→`main` only at a passed gate with three-lead approval. **Demo from `v1.0-demo`, never from `dev`.**

**Never:** push to `main`/`dev` directly · commit `.env`, keys, audio, model weights, personal data or files >5 MB · edit another team's directory · change a contract inside a feature PR · install or call anything external without asking · skip a safety-invariant test · merge `type:feature` after Day 12 noon.

## 27. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Assistant says something harmful | Project-ending with a mental-health panel | Bounded intent set; validator in code; fixed scripts; red-team table; counsellor review of SX |
| Expo dev build with mic+speaker fights the team | High — on the critical path | Two people Day 1; escalate at the Day 2 checkpoint; mobile-web fallback decided at the Day 4 gate |
| Fixed scripts (AI-003) late | High — blocks two teams | Named owner, due Day 3, checked at every checkpoint. It is a writing task and engineers defer writing |
| Scenario corpus (AI-008) late | Severe | Scripts drafted Day 1, recording calendared, treated as blocking |
| Turn latency feels broken | High | Assessment path parallel; fixed turns pre-synthesised; measured from Day 4 |
| Assessment leaks to the victim client | Severe — ethics failure in front of the panel | Server-side role fan-out with an asserting test |
| Integration failure in week two | Fatal | Contracts frozen Day 1; gates at 4 and 8; twice-daily checkpoints from Day 5 |
| LLM unavailable at the venue | Moderate | Per-intent fallbacks; demonstrate LLM-off mode live |
| Scope creep (22 languages, telephony, open chat) | Moderate | Fixed MVP scope; everything else on the roadmap slide |

---

# PART E — PRESENTATION AND FUTURE

## 28. The 90-second demo

Consent screen with AI disclosure → assistant greets in Hindi and identifies itself as an AI → victim describes a threat received after filing a complaint → assistant acknowledges and asks the licensed safety question → on the console the transcript streams, the structured record fills itself, the SVI climbs Moderate → High with the triggering sentence highlighted → victim speaks the scripted crisis line → intake stops, the fixed crisis script plays, band goes Critical at the top of the queue with an audible alert → the executive opens the packet, confirms counselling and legal aid with policy citations, rejects one recommendation with a reason, and takes over the live session → the victim hears in Hindi that a person has joined → the timeline shows "officer assigned".

Close: *the AI listened, structured and flagged; the officer decided; and she told her story once.*

## 29. Prepared answers

| Question | Answer |
|---|---|
| Why can I not call a real number? | Adapter-ready architecture; the telephony adapter stub is in the repository; live 14566 integration needs departmental approval, an authorised operator and DLT registration — weeks of integration, not a redesign. We built and validated everything downstream of the channel |
| What if the AI says the wrong thing to a victim? | It cannot say anything outside an approved intent set. Deterministic state machine, LLM phrases only, validator checks before speaking. Here is the guardrail file and here is our red-team table |
| What if someone is suicidal? | Intake stops, a fixed pre-approved script plays, the case goes Critical to the top of the queue, a human is asked to take over. No model decides whether to escalate. We can trigger it right now |
| Can AI assess trauma? | It cannot and we do not claim it. The SVI is an assistive prioritisation indicator from nine transparent dimensions with published weights labelled provisional pending expert calibration. Acoustic emotion is one auxiliary signal. Nothing here is a diagnosis |
| Is this a GPT wrapper? | No, and we will show you. With the LLM disabled the assistant still runs the intake from pre-written fallbacks, the detectors still fire and the SVI still computes |
| Where does the victim's data go? | Nowhere. Speech recognition, synthesis, acoustics and classifiers all run on this machine. No third party ever receives a victim's voice |
| Who decides? | A human executive, always, with the decision recorded separately from the AI output, a written reason required for any band override, and a complete audit trail |

## 30. Roadmap beyond the MVP

Authorised telephony and IVRS connectors for 14566 through a licensed operator, plus Integrated Portal and existing chatbot — all against the ingestion interface already in the codebase · progressive rollout across the 22 scheduled languages via IndicConformer and Indic Parler-TTS, each gated by its own evaluation, with dialect adaptation · formal clinical governance sign-off of the dialogue scripts and crisis protocol by mental-health professionals and NHAA operational staff · expert calibration study replacing the provisional SVI weights against real triage outcomes · governed domain dataset under an approved framework with a documented lawful basis · SAFE-SIGNAL multimodal model replacing the rule-based prototype, published as a study · full-duplex low-latency voice via a media server · district and state analytics for resource allocation and rehabilitation follow-up · production monitoring with drift detection and automation-bias auditing of executive acceptance rates.

## 31. Glossary

**SVI** Stress Vulnerability Index, 0–100, nine weighted dimensions · **Band** Low/Moderate/High/Critical · **D1–D9** the nine dimensions · **SX** the crisis interrupt state · **SH** human handoff state · **SAFE-SIGNAL** cross-modal divergence check between text severity and acoustic distress · **Escalation packet** the decision-ready case bundle handed to an executive · **Executive** helpline officer with decision authority · **Licensed question** the single question a dialogue state permits · **Intent** an approved assistant utterance type · **Fallback** pre-written sentence used when the LLM is unavailable or its output is rejected · **Abstention** returning `needs_human` instead of a score · **Adapter-ready** every channel terminates at one normalised ingestion interface · **NHAA** National Helpline Against Atrocities (14566) · **DPDP** Digital Personal Data Protection Act 2023 · **DLT** Distributed Ledger Technology registration required by TRAI for commercial voice and SMS in India.

---

# END OF HANDOVER

**If you are an AI assistant:** acknowledge in three lines — confirm you have the handover, state the current phase and next gate, and name the single most urgent unstarted task from §21. Then wait. Do not summarise this document back.
