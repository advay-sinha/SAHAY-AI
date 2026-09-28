# SAHAY-AI

**AI-assisted intake, vulnerability assessment and human escalation for victim helplines.**

SAHAY-AI receives a victim's first contact by voice or text, runs a strictly bounded
intake conversation, builds a structured case profile with a **Stress Vulnerability
Index (SVI)** and per-claim evidence, and hands that packet to a human helpline
executive who makes every decision. The victim gets a status timeline and never has to
retell their account at the next stage.

The assistant is a **bounded intake instrument, not a chatbot and not a counsellor**.
A deterministic state machine picks the intent; a language model may only phrase it; a
validator checks the sentence before it is spoken; if validation fails, pre-written
text is used instead.

> **Prototype.** No clinical validity is claimed, SVI weights are provisional and
> pending expert calibration, and the system must never be run against real victim
> data in this state.

---

## Table of contents

- [Why it exists](#why-it-exists)
- [Safety invariants](#safety-invariants)
- [How a session works](#how-a-session-works)
- [Stress Vulnerability Index](#stress-vulnerability-index)
- [AI models and evaluation](#ai-models-and-evaluation)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Frozen contracts](#frozen-contracts)
- [Latency budget](#latency-budget)
- [Getting started](#getting-started)
- [Running the stack](#running-the-stack)
- [Verification](#verification)
- [External dependency policy](#external-dependency-policy)
- [Documentation map](#documentation-map)
- [Contributing](#contributing)
- [Current status and known gaps](#current-status-and-known-gaps)

---

## Why it exists

Helplines have no standardised way to assess the psychological condition and
vulnerability of a caller at first contact. Distressed people are triaged by whoever
answers, with no consistent record of severity, no prioritisation signal, and a burden
on the victim to repeat a traumatic account at every stage.

SAHAY-AI addresses exactly that gap and nothing wider:

| Need | How it is met |
|---|---|
| Consistent severity signal at first contact | Deterministic, weighted 9-dimension SVI with bands and hard overrides |
| Evidence behind every claim | Each dimension carries a score, a confidence and the turn IDs that support it |
| No repetition of the account | Structured case packet persists and follows the case |
| Human authority | Every recommended action requires explicit executive confirmation |
| Uncertainty handled honestly | Low confidence or poor audio returns `needs_human: true` and **no score** |
| Privacy | Speech, acoustics and classifiers are self-hosted; victim audio never leaves the deployment |

## Safety invariants

These are not features and are not negotiable. If one of them would have to be cut to
make a deadline, features get cut instead.

1. **The assistant never speaks freely.** A deterministic state machine selects one
   approved intent, the LLM only phrases it, and `guardrails.validate()` checks the
   output before synthesis. No free-form generation reaches a victim.
2. **The crisis interrupt is unconditional.** Crisis or self-harm language is detected
   by a synchronous pre-check that runs *before* dialogue policy. A match forces state
   `SX`, plays a fixed pre-approved script, raises Critical and requests immediate
   human takeover. Intake never resumes automatically, and no model decides whether to
   escalate.
3. **Assessment data never reaches the victim.** No SVI, band, dimension, emotion,
   confidence or alert in the victim app, portal or timeline. Enforced server-side by
   role-filtered fan-out in `backend/app/ws/fanout.py`, with asserting tests on both
   the server and the client.
4. **A human decides everything.** AI recommendations and human decisions live in
   separate tables (`decisions_ai`, `decisions_human`) so no record can read as though
   a machine decided.
5. **Hard overrides beat weighted scores.** Confirmed immediate danger (D1) or crisis
   (D2) forces band = Critical regardless of the weighted sum.
6. **Abstention is a valid output.** Aggregate confidence below `0.45`, poor audio
   quality or low language confidence returns `needs_human: true` and no score.
7. **AI disclosure is permanent** and *"talk to a person"* is a one-tap control that
   transfers immediately, available at every point of the intake.
8. **Nothing external is added without an explicit recorded decision.** See
   [External dependency policy](#external-dependency-policy).

## How a session works

The state machine is defined in `docs/dialogue/STATES.md` and implemented in
`ml/dialogue/`. States are **skippable and reorderable** — if the free narrative
already answered a state, it is skipped. Target length is 8-12 turns; this is a first
contact, not an interview. The chat channel uses the identical state machine, minus
ASR and TTS.

| State | Purpose |
|---|---|
| `S0` Opening | Fixed, pre-recorded script: identifies the assistant as an AI, states that a human officer reviews everything and that a human is available at any time |
| `S1` Free narrative | Listen. Brief neutral acknowledgement. No probing, no interruption |
| `S2` Immediate safety | Can the person who caused harm reach them right now |
| `S3` Medical need | Whether anyone needs medical help now — never asks for injury detail |
| `S4` Who and when | Fills only the gaps the narrative left |
| `S5` Ongoing threat | Continuing pressure, intimidation, witness risk |
| `S6` Support network | Isolation, boycott, displacement |
| `S7` Existing action | Complaint/FIR status, legal help |
| `S8` What they want | The stated need of the person, kept as a first-class field |
| `S9` Closing | Fixed, pre-recorded script: confirms the account is recorded, gives a reference, states next steps. **No promises of outcome** |
| `SX` Crisis interrupt | Reachable unconditionally from any state. Fixed script, Critical, human takeover. Does not return to intake |
| `SH` Human handoff | Reachable from any state on request or escalation; holds the session for the executive |

Every utterance is one sentence, plain words, and only the question the state licenses.
The validator rejects advice (legal, medical, procedural), diagnosis, promises about
outcomes, requests for graphic detail, asking "why", and minimising comfort language —
in both Hindi and English. Every intent has a written fallback in both languages, so
the full dialogue runs with the LLM disabled (`LLM_PROVIDER=mock`).

## Stress Vulnerability Index

`svi.compute(dimension_scores, confidences, quality)` is a pure function — standard
library only, no I/O, no model loading — so it is fully testable and explainable.

| Dim | Meaning | Weight |
|---|---|---:|
| D1 | Immediate safety threat | 0.22 |
| D2 | Crisis / self-harm language | 0.18 |
| D3 | Fear, intimidation, threats | 0.13 |
| D4 | Acute distress (acoustic + emotional) | 0.12 |
| D5 | Trauma-associated indicators | 0.08 |
| D6 | Social isolation, boycott, displacement | 0.08 |
| D7 | Medical urgency | 0.08 |
| D8 | Legal urgency | 0.06 |
| D9 | Communication safety | 0.05 |

`SVI = Σ(weight_i × score_i)`, dimension scores 0-100.

**Bands:** 0-29 Low · 30-54 Moderate · 55-74 High · 75-100 Critical.

**Hard overrides, which beat the weighted sum:**

- confirmed D1 or D2 above threshold ⇒ band = Critical
- aggregate confidence < 0.45, poor audio quality, or low language confidence ⇒
  `needs_human: true` and **no score at all**
- consent declined ⇒ scoring suppressed entirely

Weights are labelled **provisional, pending expert calibration** wherever they are
shown in the UI.

## AI models and evaluation

The **deterministic pipeline is authoritative**: the crisis pre-check, the rule-based
detectors, the output validator and the SVI engine. Every trained model is compared
against it and runs in **shadow**: its output is shown beside the rules in the local ML
demonstration, but it never routes, scores or speaks.

| Component | What it is | Status |
|---|---|---|
| Crisis pre-check and detectors | Lexicons with clause-scoped negation and attribution cues, in English, Hindi and Hinglish | **Authoritative** |
| Output validator | 87 phrase rules plus licensed-question checks, applied before any sentence is spoken | **Authoritative** |
| SVI engine | Weighted sum with hard overrides and abstention | **Authoritative**; weights provisional |
| Speech-to-text | Whisper Small behind Silero VAD, in a loopback-only local service (PC-11) | In the voice path; Hindi WER not yet measured |
| D4 voice distress | A rule comparing a caller's pitch, loudness and pauses with their own first turns | Wired; unvalidated |
| Speech emotion (SER) | emotion2vec+, Whisper-encoder and WavLM heads, trained on acted English speech | Shadow; off in D4 until its gate passes on team recordings |
| Text affect | MuRIL fine-tuned on EmoInHindi and GoEmotions | Shadow |
| Shadow safety detector (Stage W) | MuRIL with borrowed weak labels (Reddit crisis, Dreaddit stress, hate speech) plus a fictional corpus | Shadow; `rejected_for_product_integration` |
| Voice output | Human-recorded fixed scripts plus the built-in offline Windows voice (PC-12) | Wired; nothing spoken until the scripts are approved |

Measured results:
- **Evidence class.** All numbers below come from fixtures published during
  development: they show regression behaviour, not generalisation. The locked set has
  **0** samples, so nothing is official.
- **Rules.** On development fixtures they miss 0 of 17 critical events; on candidate
  fixtures, 1 of 14. The crisis pre-check finds 9 of 9 and 8 of 9 crisis cases.
  Detector micro F1 is 0.93 and 0.88.
- **Red team.** 39 of 39 cases blocked before synthesis.
- **Shadow MuRIL.** It reaches 0.99 AUROC on Reddit crisis text, where the rules find
  0.38 of posts. On SAHAY's own fixtures it reaches only 0.56–0.62 micro F1 against the
  rules' 0.93 and 0.88, and it fires on harmless absence wording.
- **Latency** (laptop, synthetic speech). A server-side voice turn takes 581 ms at p95;
  adding the phone's 700 ms end-of-speech wait gives about 1.3 s, within the 3 s budget.

The full evaluation table has 150 rows, each labelled with its source and evidence
class: `ml/eval/results/eval-table-2026-09-29.md`. The judge-defence pages are in
`docs/defence/`. Every component has a card, listed in `docs/defence/README.md`.

## Architecture

```text
   Victim (Expo app: voice + chat)            Executive console (React/Vite)
                |                                        |
                |  WSS /ws/session/{id}                  |  WSS + REST
                v                                        v
        +------------------------------------------------------+
        |  FastAPI gateway                                     |
        |   - consent gate            - JWT auth + roles       |
        |   - turn loop orchestration - ROLE-FILTERED FAN-OUT  |
        +-------+------------------------------+---------------+
                | reply path (must stay < 3 s) | parallel path (never blocks)
                v                              v
   crisis pre-check -> dialogue.next ->   assessment runner
   LLM phrasing -> guardrails.validate    -> detectors, classifiers, acoustics
   -> TTS                                 -> svi.compute -> alerts -> recommendations
                |                              |
                v                              v
         victim-safe events            executive-only events + case packet
                                               |
                                               v
                                   human decision -> decisions_human -> audit
```

Providers for ASR, TTS, LLM, storage, the assessment runner and policy retrieval all
sit behind adapters with working mocks (`backend/app/adapters/`). The MVP profile is
deliberately small: the backend runs on a Supabase PostgreSQL development/demo
project through SQLAlchemy and an async driver, with a local background runner instead
of Redis/RQ and local keyword/index retrieval instead of pgvector. FastAPI is the only
database gateway — no web or mobile client ever receives a Supabase key or a database
credential. Normal startup has no SQLite fallback; disposable SQLite exists only under
`APP_ENV=test` for unit and integration tests, migration compatibility checks and the
guarded local reset/scenario scripts.

**Pure modules** — standard library only, no I/O, no network, no model loading:

```python
dialogue.next(state, slots, utterance, safety_flags)
guardrails.validate(text, intent, lang)
svi.compute(dimension_scores, confidences, quality)
```

## Repository layout

```text
backend/       FastAPI gateway — REST, WebSocket, role fan-out, workers, Alembic, seed
  app/api/       auth, sessions (incl. voice upload PC-11, turn audio PC-12), cases
  app/ws/        events, session socket, fanout (server-side role filter)
  app/services/  consent, turn loop, decisions, timeline, latency metrics
  app/adapters/  llm, asr, tts, storage, retrieval, assessment_runner (all mockable)
  scenarios/     scenario runner and the M2 latency benchmark
  tests/         role fan-out, consent gate, timeline leakage, contract mirror, auth, audio
ml/            Safety-critical and model code
  dialogue/      states, intents, policy, fixed scripts
  guardrails/    crisis pre-check, validator, banned patterns, lexicons
  svi/           dimensions, weights, engine, hard overrides
  nlp/           detectors, lexicons, slot extraction, transliteration
  acoustics/     prosody, audio quality, the D4 voice-distress rule
  voice/         loopback speech-to-text service (Whisper Small + Silero VAD)
  tts/           fixed-script recording registry, offline Windows voice
  runtime/       pinned model manifest, offline loading, benchmarks
  ser/           speech-emotion candidates (shadow)
  textaffect/    MuRIL text affect (shadow)
  training/      Stage A/B/C/W training, logistic baseline, shortcut check (shadow)
  data/          dataset governance, label firewall, corpus builders
  eval/          deterministic evaluation harness, evaluation table, defence pages
frontend/      React + Vite executive console — queue, case packet, decisions, audit
mobile/        Expo victim app — consent, voice, chat, timeline, offline queue
data-scripts/  Corpus manifest and dataset registry (metadata only, never media)
docs/          Specification, frozen contracts, dialogue states, phase plan, decisions
scripts/       PowerShell launch and verification scripts (never install anything)
runtime/       Local-only artefacts: db, audio, logs, cache, policy index (git-ignored)
```

## Frozen contracts

`docs/contracts/CONTRACTS.md` is the single source of truth every team builds against —
not another team's current code. It changes only through an approved `type:contract`
change with all leads agreeing, never inside a feature PR.

**Transport**

```text
WSS /ws/session/{session_id}?token=<jwt>

UP    binary  16 kHz mono PCM16 - 500 ms frames - 8-byte header: uint32 seq | uint32 ms
      text    {"type":"chat.message","text":...,"lang":...} and {"type":"request_human"}
DOWN  binary  assistant TTS chunks, prefixed with a turn_id header
      text    events below

FALLBACK      POST /sessions/{id}/audio   whole-utterance upload, always available
RECONNECT     client resumes from last acknowledged seq; server de-duplicates
```

**Events a victim client may receive**

```text
assistant.turn    {turn_id, text, lang, intent, audio}
transcript.line   {turn_id, speaker, text, lang, ts}
session.status    {state, consent, lang, human_joined}
timeline.update   {stage, label, ts}
```

**Events restricted to the executive console** — filtered server-side by role; a
client-side filter is not acceptable:

```text
dimension.update - alert.safety - case.structured
action.recommended - safesignal.flag - escalation.packet
```

**REST**

```text
POST /auth/login
POST /sessions | POST /sessions/{id}/end
POST /sessions/{id}/audio?lang=hi|en        whole-utterance voice turn (PC-11) -> {turn_id, status}
GET  /sessions/{id}/turns/{turn_id}/audio   assistant-turn audio (PC-12) -> audio/wav, or 404
GET  /queue
GET  /cases/{id}            full escalation packet
POST /cases/{id}/claim | /cases/{id}/takeover
POST /cases/{id}/decisions  {action_id, decision, rationale, officer_id}
POST /cases/{id}/override   {band, reason}   # reason REQUIRED
GET  /cases/{id}/timeline   victim-safe view — contains no assessment field
GET  /cases/{id}/audit
```

`backend/tests/test_contract_mirror.py` is the drift guard. It reads
`docs/contracts/CONTRACTS.md`, `backend/app/ws/events.py`, `ml/svi/dimensions.py` and
`frontend/src/types/contracts.ts` as text and fails if the four disagree on the event
allowlists, the SVI weights, the band thresholds or the abstention floor. Three
hand-maintained copies of one contract will otherwise drift, and the failure mode is an
assessment event reaching a victim client.

## Latency budget

The reply path is budgeted end to end. Assessment runs on a parallel path and must
never block a reply.

| Stage | Target | Measured, p95 (laptop, synthetic speech) |
|---|---|---|
| VAD endpoint | ~700 ms silence | configured on the phone; not measured |
| ASR final (utterance) | <= 0.6 s | 572 ms for the speech-to-text request |
| Safety pre-check | <= 0.05 s | 0.1 ms |
| Dialogue policy | <= 0.01 s | 0.1 ms |
| LLM phrasing | <= 0.8 s | not exercised (mock LLM) |
| Output validator | <= 0.02 s | not exercised (no generated text) |
| TTS first chunk | <= 0.5 s (0 s for pre-synthesised turns) | 38 ms (offline English voice) |
| **Victim stops speaking → assistant starts** | **< 3 s** | server voice turn 581 ms; about 1.3 s with the 700 ms end-of-speech wait. Wi-Fi and the phone are not yet measured |

Timings are recorded per turn in `latency_metrics`. `backend/scenarios/latency_benchmark.py`
reproduces the table: `ml/eval/results/latency-2026-09-29.md`.

## Getting started

### Prerequisites

| Tool | Version | Note |
|---|---|---|
| Git | any recent | |
| CPython | 3.11.9 | installs alongside newer interpreters; wheel coverage is better than 3.13 |
| Node.js | 24 LTS | both `frontend` and `mobile` declare `"engines": ">=24.0.0 <25.0.0"` |
| Android phone | physical device | only needed for the mobile gate |

FFmpeg, the Android SDK, Docker and Redis are deliberately **not** prerequisites and
stay deferred until a feature needs them. The backend does require an explicitly
configured Supabase PostgreSQL development/demo project — see
[Configuration](#configuration).

### Setup

```powershell
git clone <repository-url> sahay-ai
cd sahay-ai
.\scripts\check-prerequisites.ps1     # read-only presence/version check
copy .env.example .env                # then fill SECRET_KEY locally
```

Separate virtual environments are used for `backend/.venv` and `ml/.venv`; frontend and
mobile keep independent `package.json` and lockfiles. Never install project packages
globally, and keep datasets and model weights in a sibling directory outside the
repository.

### Configuration

`.env` is git-ignored and must never be committed. Notable keys:

| Key | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | Supabase connection string | PostgreSQL through SQLAlchemy; direct connection with IPv6, or the **Session pooler on port 5432** on IPv4-only machines. Transaction pooling on 6543 is rejected |
| `MIGRATION_DATABASE_URL` | empty | Separate migration-safe connection for Alembic, when one is available |
| `DATABASE_POOL_SIZE` | `5` | Pool sizing; see `.env.example` for the overflow and timeout keys |
| `SUPABASE_PROJECT_REF` | empty | Remote demo seeding stays denied unless this and the seed gates are satisfied |
| `LLM_PROVIDER` | `mock` | The whole dialogue must run with the LLM disabled |
| `ASR_PROVIDER` | `mock` | `local_service` calls the loopback speech-to-text process (`python -m ml.voice.service`) |
| `ASR_SERVICE_URL` | `http://127.0.0.1:8765` | Loopback only; anything else is refused |
| `TTS_PROVIDER` | `none` | `windows_voice` speaks validated turns with a built-in offline voice; `none` shows text only |
| `FIXED_AUDIO_ROOT` | `./runtime/audio/fixed` | Approved human recordings of S0, S9, SX, SH (`python -m ml.tts.presynth status`) |
| `ASSESSMENT_RUNNER` | `local` | Background runner; never on the reply path |
| `POLICY_RETRIEVER` | `local` | Deterministic local retrieval |
| `SVI_CONFIDENCE_FLOOR` | `0.45` | Below this, abstain: `needs_human`, no score |
| `TURN_LATENCY_TARGET_MS` | `3000` | Reply-path budget |
| `AUDIO_RETENTION_HOURS` | `72` | Local audio retention window |
| `HOST` | `0.0.0.0` | Required so a physical phone can reach the laptop |

Local console accounts (`exec1`, `exec2`, `sup1`) are created by
`backend/seed/seed.py` from `SEED_PASSWORD`, or a generated password printed once. No
credential is committed, bundled into the frontend or prefilled on the login page, and
these accounts must never be reused with real case data.

### Ports

| Process | Port |
|---|---:|
| FastAPI HTTP + WebSocket | 8000 |
| Vite executive console | 5173 |
| Expo Metro | 8081 |

A phone connects to the LAN IPv4 address of the machine, not `localhost`.

## Running the stack

```powershell
.\scripts\start-backend.ps1     # FastAPI from backend/.venv
.\scripts\start-frontend.ps1    # Vite console
.\scripts\start-mobile.ps1      # Expo victim app
.\scripts\reset-db.ps1          # rebuild the disposable local SQLite test DB (prompts first)
```

None of these scripts install or download anything; they use dependencies only after
those dependencies have been approved and installed.

## Verification

The safety-critical modules are dependency-free on purpose, so the checks that matter
most run on a bare interpreter:

```powershell
python -m unittest discover -s ml/tests -t .        # dialogue, guardrails, SVI, purity
python -m unittest discover -s backend/tests -t .   # role fan-out, consent, timeline leakage, contract mirror
node --test "mobile/tests/*.test.js"                # no assessment data in the victim app
```

`.\scripts\verify-local.ps1` runs the full gate in two tiers:

- **Tier 1** — needs nothing installed: ML pure modules, backend safety tests, mobile
  leakage and i18n tests.
- **Tier 2** — needs installed dependencies: backend pytest and lint, frontend
  typecheck/build/lint and contract tests, mobile typecheck. A missing virtual
  environment or `node_modules` reports `BLOCKED` rather than silently weakening the
  check.

Evaluation, regenerated from result files:

```powershell
python -m ml.eval.run_eval --out ml/eval/results --tag <date>                  # deterministic safety evaluation
python -m ml.eval.table --eval-json ml/eval/results/eval-<date>.json --out ml/eval/results --tag eval-table-<date>
python -m ml.eval.defence --eval-json <eval json> --table-json <table json> --out docs/defence
backend\.venv\Scripts\python.exe backend\scenarios\latency_benchmark.py --rounds 3   # M2 latency
```

Checks a script cannot make, and that are part of the definition of done:

- the phone reaches the LAN IPv4 address of the host machine
- the crisis interrupt reaches a human, by hand, with a real voice
- the victim client receives no assessment event, observed on the wire
- the full demo scenario, on the actual demo machine

## External dependency policy

Nothing is approved merely because it appears in this repository. Before any new
package, model, dataset, API, credential, database, service, or network fetch, the
change must be proposed and recorded in `docs/EXTERNAL_DECISIONS.md` with item,
version, purpose, licence, size, demo risk and the fallback if declined. Statuses are
`PROPOSED`, `APPROVED`, `DECLINED` and `REVOKED`; approval covers the exact item and
scope recorded, and never an alternative or an upgrade.

Standing defaults:

- Speech, acoustics and classifiers are **self-hosted only** — victim audio never
  leaves the machine.
- Telephony, SMS, messaging and push notifications are out of scope.
- An LLM is permitted only behind an adapter with a working mock, and the system must
  run fully with it disabled.
- Docker, CI/CD, Redis, pgvector and any wider cloud deployment are deferred.

Secrets are placed in the ignored `.env` locally and are never pasted into
documentation, issues, commits or chat.

## Documentation map

| Document | What it governs |
|---|---|
| `CLAUDE.md` | Operating rules for the repository, including per-directory instructions |
| `docs/HANDOVER.md` | Complete product and safety specification |
| `docs/contracts/CONTRACTS.md` | Frozen interfaces — transport, events, REST, SVI, latency |
| `docs/dialogue/STATES.md` | Permitted states, licensed questions and fixed scripts |
| `docs/dialogue/FIXED_SCRIPTS_REVIEW.md` | Decisions required before any fixed script is drafted |
| `docs/plan/PHASES.md` | Build sequence, phase gates and the cut order |
| `docs/LOCAL_SETUP.md` | Machine and repository setup |
| `docs/DATASETS_AND_SERVICES.md` | Approved and deferred external assets |
| `docs/EXTERNAL_DECISIONS.md` | Decision log for every external dependency |
| `docs/TEAM-OPERATIONS.md` | Ownership, reviews and integration workflow |
| `docs/plan/ML_NATIONAL_MVP.md` | ML phase plan: what is done, what is measured, what is left |
| `docs/defence/` | Judge-defence pages: headline numbers, red team, limitations, Q&A, card index |
| `ml/eval/results/` | Evaluation runs, the evaluation table and the latency report |
| `ml/eval/CONTAMINATION.md` | Which fixtures are exposed, and why their results are regression evidence |
| `docs/research/local-research-analysis.tex` | The research analysis (PDF alongside) |
| `docs/plan/human-tasks/` | The human tasks (H1–H13) that the remaining verification depends on |
| `CONTRIBUTING.md` | Branch naming, commits, review rules, definition of done |

## Contributing

Read `CONTRIBUTING.md` before the first commit. In short:

- Branches are `<type>/<team>-<description>`; commits follow Conventional Commits.
- One reviewer from another team for normal changes; **all leads** for contract or
  schema changes; **two reviewers**, one running the dialogue-safety review, for
  anything touching dialogue, crisis handling or guardrails.
- The integration owner runs `scripts/verify-local.ps1` before merging to `dev`.
  `main` stays demo-ready.
- Never commit secrets, `.env`, audio or video, datasets, databases, model weights,
  generated media, real personal data, or files over 5 MB. Commit manifests,
  checksums, scripts and aggregate results instead.

A task is done when its focused tests pass, manual verification passes, the safety
contracts are intact, documentation accompanies any contract or dialogue change,
external decisions are recorded, and user-facing work has been checked on the actual
demo machine or a physical phone.

## Current status and known gaps

This is a working prototype under active development, and the gaps are stated rather
than hidden:

- **The fixed scripts for `S0`, `S9`, `SX` and `SH` are not yet written.**
  - They must be authored in Hindi and English, and reviewed (`SX` by a counsellor or
    psychology faculty member).
  - They are then recorded by people and approved in the recording registry.
  - They are never model-generated, and the code fails closed until then.
- **No independent evaluation exists yet.** The locked set has 0 samples and the blind
  corpus is not written. Every safety number is exposed regression evidence.
- **Speech emotion, text affect and the shadow MuRIL detector stay shadow-only.** The
  speech-emotion gate needs team recordings in Hindi and English.
- **Still unmeasured:** Hindi word error rate, and latency on a real phone over Wi-Fi.
  There is no Hindi voice on the demo laptop, so Hindi replies are shown as text.
- **Lexicon changes are drafts until two people review them:** crisis lexicon,
  detector lexicons, output rules.
- **The remaining verification is human work.** See `docs/plan/human-tasks/` (H1–H13)
  and Section 14 of the research analysis.
- SVI weights are provisional and have not been calibrated by domain experts.
- Language support is limited to what has actually been tested; no claim is made for
  untested languages or dialects.
- Docker, CI/CD, Redis, pgvector and any wider cloud deployment are deferred.
- No clinical validity, diagnosis or production readiness is claimed.
- **Real victim data must never be used with this build.**
