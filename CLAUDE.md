# SAHAY-AI — Claude Master Instructions

Read this file before taking any action. Then read the `CLAUDE.md` inside the directory you will change, followed by the relevant specification under `docs/`.

## 1. Project and operating mode

SAHAY-AI is an AI-assisted intake, vulnerability assessment and escalation prototype for NHAA 14566, Problem Statement 26093, Ministry of Social Justice and Empowerment.

The MVP runs entirely on one Windows development/demo machine:

- FastAPI and local Python processes
- SQLite through SQLAlchemy
- React/Vite executive console
- React Native/Expo victim application
- local audio/model/data directories outside Git
- mock LLM by default
- manual verification scripts

Docker, CI/CD, PostgreSQL, Redis, pgvector and cloud deployment are deferred. Do not introduce them unless the user explicitly approves them through the external-dependency protocol below.

Authoritative documents:

- `docs/HANDOVER.md` — complete product and safety specification
- `docs/contracts/CONTRACTS.md` — frozen interfaces
- `docs/dialogue/STATES.md` — permitted dialogue states and scripts
- `docs/plan/PHASES.md` — local-first build sequence and gates
- `docs/LOCAL_SETUP.md` — machine and repository setup
- `docs/DATASETS_AND_SERVICES.md` — approved and deferred external assets
- `docs/EXTERNAL_DECISIONS.md` — decision log

## 2. Non-negotiable safety invariants

1. A deterministic state machine chooses one approved intent. An LLM may only phrase that intent. Validate every generated sentence before synthesis; use a pre-written fallback when validation fails.
2. Detect crisis/self-harm language before normal dialogue policy. A match forces state SX, a fixed approved script, Critical priority and immediate human takeover. Intake never resumes automatically.
3. Victim clients never receive SVI, band, dimension, emotion, confidence, assessment or alert data. Enforce this server-side and test it.
4. A human decides every recommended action. Keep AI recommendations and human decisions in separate tables and payloads.
5. Confirmed immediate danger or crisis overrides the weighted score and forces Critical.
6. Low confidence, poor audio or low language confidence returns `needs_human: true` and no score.
7. AI disclosure remains visible and “Talk to a person” remains available throughout intake.
8. Never use real victim data in the MVP.

If a request would break one of these rules, refuse that part and explain which invariant it violates.

## 3. External dependency protocol — mandatory

Before doing any of the following, stop and ask the user:

- installing or upgrading a Python, npm or system package
- downloading a dataset, model, checkpoint, voice or binary
- calling an external API or enabling network access at runtime
- adding an API key, credential, endpoint or environment variable
- adding a database, cache, queue, vector store or cloud service
- enabling Docker, CI/CD or deployment
- fetching policy documents or other files from the internet

First inspect `docs/EXTERNAL_DECISIONS.md`. If the exact item, version, purpose and scope are already marked **APPROVED**, proceed without asking again. Otherwise show:

```text
EXTERNAL DEPENDENCY — decision needed

What:         <exact item and version/release>
Why:          <task it unblocks>
Where:        <team and files>
Licence/cost: <licence, access terms and cost>
Size/runtime: <download/disk/RAM and CPU/GPU requirements>
Demo risk:    <offline status, key, rate limit and failure mode>
If declined:  <fallback to implement>

Proceed?
```

Wait for an explicit answer. If approved, record the date, scope and exact item in `docs/EXTERNAL_DECISIONS.md` in the same change. Approval for one item does not approve alternatives or upgrades. Never ask for a secret value in chat or commit it; ask the user to place it in `.env` locally.

## 4. Recommended initial external set

Nothing is approved merely because it appears in this repository. The user must approve the initial batch once before Claude downloads or installs it:

- pinned dependencies already declared in repository requirements/lockfiles
- Mozilla Common Voice Hindi, selected release and evaluation splits only
- RAVDESS `Audio_Speech_Actors_01-24.zip` only
- faster-whisper `small` model for local CPU int8 inference
- Silero VAD model

The locally scripted scenario corpus requires no download but its scripts and labels require human review. Everything else remains deferred.

## 5. Local architecture rules

- Use `sqlite+aiosqlite` locally but keep persistence behind SQLAlchemy so PostgreSQL can be added later.
- Use a local assessment-runner interface. The local implementation may use `asyncio.to_thread`; normal assessment must never block the reply path.
- The crisis pre-check stays synchronous and executes before dialogue policy.
- Put policy retrieval behind an interface. Start with a small local index or deterministic keyword retrieval.
- Keep ASR, TTS, LLM, storage, assessment runner and retrieval providers behind adapters with mocks.
- The complete dialogue must run with `LLM_PROVIDER=mock`.
- Model weights, audio, datasets, databases and generated media remain outside Git.
- Use manual verification through `scripts/verify-local.ps1`; CI is currently deferred.

## 6. Pure modules

These modules use the Python standard library only and perform no I/O, network access or model loading:

```python
dialogue.next(state, slots, utterance, safety_flags)
guardrails.validate(text, intent, lang)
svi.compute(dimension_scores, confidences, quality)
```

## 7. Repository ownership

| Area | Owner |
|---|---|
| `ml/`, `data-scripts/` | AI/ML and Safety lead |
| `backend/` | Backend lead |
| `frontend/` | Executive Web lead |
| `mobile/` | Mobile / Victim Experience lead |
| `docs/contracts/`, `docs/dialogue/` | All four leads (D-11) |
| `scripts/`, local integration | Integration owner |

Never silently change a frozen contract. Propose the exact change and record lead approval before implementation.

## 8. Definition of done

A task is done only when its focused tests pass, manual verification passes, safety contracts remain intact, documentation changes accompany contract/dialogue changes, external decisions are recorded, and user-facing work has been checked on a real phone or the actual demo machine.

## 9. Working style

Prefer the smallest mechanism that passes the current gate. Report measured results. Do not claim clinical validity, diagnosis, production readiness or support for untested languages. Do not add Docker, cloud infrastructure, telephony, messaging, a new model, or a new dataset because it may be useful later.
