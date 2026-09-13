# External Dependency Decision Log

Claude reads this file before any install, download, API use or service addition. A planned item is not approved. The user or project owner changes status only after reviewing Claude's dependency request.

## Status values

- `PROPOSED` — not approved; Claude must ask.
- `APPROVED` — Claude may use the exact item and scope recorded.
- `DECLINED` — implement the recorded fallback.
- `REVOKED` — stop new use and follow the recorded migration action.

## Initial decisions pending

| ID | Item | Exact scope | Purpose | Status | Decision date | Decided by | Notes/fallback |
|---|---|---|---|---|---|---|---|
| EXT-001 | Repository Python/npm packages | Exact pinned manifests + generated lockfiles | Local application development | APPROVED | 2026-09-10 | Project owner | Installed and verified; all 7 local checks pass |
| EXT-002 | Mozilla Common Voice Hindi | One named release; selected Hindi evaluation splits | ASR WER/CER | PROPOSED | | | Use own corpus for smoke tests |
| EXT-003 | RAVDESS | Audio_Speech_Actors_01-24.zip only | Auxiliary SER baseline | PROPOSED | | | Use own scripted audio only |
| EXT-004 | faster-whisper | small model; CPU int8 local use | ASR | PROPOSED | | | Text input and transcript fixtures |
| EXT-005 | Silero VAD | One pinned model/release | Endpointing | PROPOSED | | | Manual whole-utterance submit button |
| EXT-113 | Node.js runtime target | Node.js 24.19.0 LTS; `engines` >=24 <25 | Frontend and mobile toolchain | APPROVED (amended) | 2026-09-10 | Project owner | Amended from Node 22: winget no longer offers 22 under OpenJS.NodeJS.LTS |
| EXT-114 | CPython 3.11.9 (Windows x64) | Interpreter only, alongside existing 3.12 and 3.13.2 | backend/.venv and ml/.venv | APPROVED (installed) | 2026-09-10 | Project owner | Installed 2026-09-10; 3.12/3.13 untouched |

## Deferred decisions

| ID | Item | Status | Earliest phase |
|---|---|---|---|
| EXT-101 | FFmpeg | PROPOSED | When audio conversion is implemented |
| EXT-102 | Android SDK/ADB | PROPOSED | When physical-phone testing starts |
| EXT-103 | TTS model/voice | PROPOSED | After fixed prompt scripts are approved |
| EXT-104 | CREMA-D | PROPOSED | P2 |
| EXT-105 | Dreaddit | PROPOSED | P2 |
| EXT-106 | MuRIL/IndicBERT/XLM-R weights | PROPOSED | P2 |
| EXT-107 | External LLM API and key | PROPOSED | P2 optional |
| EXT-108 | Official policy document corpus | PROPOSED | P2 |
| EXT-109 | Docker and Docker Compose | PROPOSED | After local full-flow gate |
| EXT-110 | PostgreSQL and pgvector | PROPOSED | Packaging/production hardening |
| EXT-111 | Redis and RQ | PROPOSED | Load/resilience hardening |
| EXT-112 | CI/CD | PROPOSED | Repository hardening |

## Decision log

```text
Date:            2026-09-10
ID:              EXT-114
Item:            CPython 3.11.x, Windows x64 installer
Decision:        APPROVED
Scope:           Interpreter installed alongside the existing Python 3.13.2. Used
                 for backend/.venv and ml/.venv only. Installing the interpreter
                 does NOT approve any Python package; EXT-001 remains PROPOSED.
Reason:          docs/LOCAL_SETUP.md pins 3.11. The machine has only 3.13.2, and
                 several dependencies expected later (faster-whisper, ctranslate2)
                 have patchy 3.13 wheel coverage.
Licence/cost:    PSF licence, free.
Location:        Machine-level install.
Fallback:        n/a — approved.
Decision maker:  Project owner, via prompt.txt on 2026-09-10.
```

```text
Date:            2026-09-10
ID:              EXT-113
Item:            Node.js 22 LTS as the project runtime target
Decision:        APPROVED (target change; no installation performed)
Scope:           `engines` field in frontend/package.json and mobile/package.json
                 set to ">=22.0.0 <23.0.0". docs/LOCAL_SETUP.md, README.md and
                 .claude/commands/setup-status.md updated in the same change.
Reason:          Node 20 has reached end of life and Node 23 is not an LTS line.
                 Neither is an acceptable target for an unattended demo machine.
                 Supersedes the "Node.js 20 LTS" line in docs/LOCAL_SETUP.md.
Licence/cost:    MIT, free.
Location:        Machine-level install, to be performed by the user.
Fallback:        n/a — approved.
Decision maker:  Project owner, via prompt.txt on 2026-09-10.
Note:            The machine currently has Node 23.7.0, which does not satisfy
                 the declared engines range. `npm install` will warn (or fail
                 under `engine-strict`) until Node 22 LTS is installed.
```

```text
Date:            2026-09-10
ID:              EXT-115
Item:            Read-only metadata requests to registry.npmjs.org and pypi.org
Decision:        APPROVED
Scope:           HTTP GET of package metadata only, to verify EXT-001 pins.
                 No tarball, wheel, model or dataset was downloaded. No paid
                 API was called. No credential was used or created.
Reason:          Pins had been written from model knowledge and needed
                 verification against the registries before approval.
Licence/cost:    Free, public, unauthenticated.
Fallback:        n/a - approved and completed.
Decision maker:  Project owner, via prompt.txt on 2026-09-10.
Result:          38 pins checked. All exist. Two incompatibilities found and
                 corrected (vitest/vite, expo-router missing peer). Six mobile
                 pins moved onto their official sdk-54 dist-tags.
```

```text
Date:            2026-09-10
ID:              EXT-001
Item:            Repository Python and npm packages
Decision:        STILL PROPOSED — manifests written, nothing installed
Scope:           Exact pinned manifests now exist at backend/requirements.txt,
                 backend/requirements-dev.txt, ml/requirements.txt,
                 ml/requirements-dev.txt, frontend/package.json and
                 mobile/package.json. No install, lockfile or node_modules was
                 produced. Awaiting an explicit approval.
Revisions
  requested by the owner and applied:
                 - expo-audio replaces the deprecated expo-av
                 - PyJWT replaces python-jose
                 - pwdlib[argon2] replaces passlib[bcrypt]
                 - runtime and development dependencies separated
                 - no ML package beyond pytest while the pure modules are built
Decision maker:  Project owner, 2026-09-10. INSTALLED AND VERIFIED.
Verification:    Completed 2026-09-10 under EXT-115. Corrections applied:
                 - frontend: vitest 2.1.8 -> 3.2.4 (2.1.8 depends on vite ^5.0.0
                   and cannot run against the pinned vite 6.0.7)
                 - mobile: @expo/metro-runtime 6.1.2 ADDED; it is a required,
                   non-optional peer of expo-router 6.0.24 and was missing
                 - mobile: expo 54.0.0 -> 54.0.37, expo-router 6.0.0 -> 6.0.24,
                   expo-constants 18.0.8 -> 18.0.14, expo-linking 8.0.8 -> 8.0.12
                   (each is the version carried by its official sdk-54 dist-tag)
                 - mobile: expo-audio 1.0.13 -> 1.0.16, expo-status-bar
                   3.0.8 -> 3.0.9 (no sdk-54 dist-tag exists for either; these
                   are the last patches of the SDK-54-era line and must be
                   confirmed with `npx expo install --check` after approval)
```

```text
Date:            2026-09-10
ID:              EXT-116
Item:            Expo SDK line for the victim app
Decision:        RECOMMENDED, awaiting approval
Scope:           Expo SDK 54 (expo 54.0.37, React Native 0.81.4, React 19.1.0).
Reason:          SDK 54 is the newest line whose full React Native and React
                 pairing can be confirmed from npm metadata alone: react-native
                 0.81.4 declares peers react ^19.1.0 and @types/react ^19.1.0,
                 which match the pinned versions exactly. SDK 55, 56 and 57
                 exist and use unified SDK-major versioning, but their React
                 Native pairing is published only in bundledNativeModules.json
                 inside the expo tarball and on the Expo docs site, neither of
                 which is within the EXT-115 metadata-only scope.
Risk:            SDK 54 is three lines behind the current SDK 57. Still
                 published and tagged, but closer to the end of its support
                 window than SDK 56 would be.
Alternative:     SDK 56 (expo 56.0.21, expo-router 56.2.20, expo-audio 56.0.13,
                 expo-constants 56.0.25, expo-linking 56.0.17).
Decision:        ACCEPTED as SDK 54. Confirmed after installation by
                 `npx expo install --check`, which reads bundledNativeModules.json
                 from the installed expo package and reported
                 "Dependencies are up to date" (exit 0).
Corrections it
  required:      expo-audio 1.0.16 -> 1.1.1
                 react-native 0.81.4 -> 0.81.5
                 @types/react 19.1.0 -> 19.1.10
                 Every other mobile pin was confirmed correct as written.
Decision maker:  Project owner, 2026-09-10.
```

```text
Date:            2026-09-10
ID:              EXT-117
Item:            Standing authorisation for routine local development
Decision:        APPROVED
Scope:           Virtual environments, installs from the approved pinned
                 manifests, lockfile generation, test/lint/typecheck/build runs,
                 local dev servers, Alembic migrations against the local SQLite
                 database, disposable local databases, ordinary source fixes and
                 documentation updates that reflect verified decisions.
Excluded:        Model training or benchmarking, dataset/weight/large-binary
                 downloads, machine-level services (FFmpeg, Android Studio, ADB,
                 Docker, PostgreSQL, Redis), paid APIs or credentials, changes to
                 the approved dependency set, `npm audit fix`, major-version
                 upgrades of Expo/React Native/React/Python/Node, Android native
                 builds, large evaluations, deletion of user files or history,
                 pushing/deploying/CI, changes to frozen contracts or safety
                 invariants, writing or activating S0/S9/SX scripts, and exposing
                 any assessment data to the mobile client.
Decision maker:  Project owner, via prompt.txt on 2026-09-10.
```

## Decision entry template

When a decision changes, append:

```text
Date:
ID and exact version/release:
Decision: APPROVED | DECLINED | REVOKED
Scope:
Reason:
Licence/cost confirmed:
Storage/runtime location:
Fallback or migration action:
Decision maker:
```

```text
Date:            2026-09-11
ID and exact
  version/release:
                 EXT-118 — SAHAY local ML model runtime
                 - google/muril-base-cased at afd9f36c…
                 - FacebookAI/xlm-roberta-base at e73636d4…
                 - openai/whisper-small at 973afd24…
                 - locally converted CTranslate2 Whisper artefact
                 - Silero VAD 6.2.1, upstream tag commit 7e30209a…
                 - exact Python package pins in
                   ml/runtime/requirements-models.txt
Decision:        APPROVED
Scope:           Private, local and offline runtime qualification on the
                 RTX 4060 laptop. MuRIL is the primary text encoder; XLM-R is
                 comparison-only. Whisper Small is approved for Hindi and
                 English transcription through the ML-owned gated pipeline.
                 Local conversion of the exact pinned official OpenAI Whisper
                 checkpoint into CTranslate2 format is approved; this does not
                 approve a third-party converted model repository.

                 GatedTranscriber is the only approved future application
                 entry point. Silero VAD must run before Whisper. Missing or
                 invalid speech intervals must be refused, and Whisper must be
                 skipped when VAD reports no speech. The private ungated path
                 is approved only for explicit synthetic worst-case
                 benchmarking and must not be exposed to application callers.

                 This approval does not authorize training, fine-tuning,
                 threshold tuning, backend/mobile integration, victim-facing
                 deployment, public network listeners, model publication,
                 redistribution, D4, or allowing model outputs to change the
                 deterministic crisis pre-check, routing or SVI.
Reason:          Hardware qualification confirmed that all four approved
                 models load and run locally with zero network attempts.
                 MuRIL and Whisper safely coexist within available VRAM.
                 VAD prevents silence and pure tones from reaching Whisper,
                 although VAD false positives and Whisper hallucination remain
                 documented limitations. Real Hindi and English recognition
                 quality has not yet been measured with approved transcribed
                 speech.
Licence/cost
  confirmed:     Free public access with no token required:
                 - MuRIL: Apache-2.0
                 - XLM-R: MIT
                 - Whisper Small: Apache-2.0
                 - Silero VAD: MIT
                 MuRIL's upstream pytorch_model.bin is accepted for this local
                 qualification because its immutable revision and hash are
                 verified and it is loaded with restricted weights-only
                 loading.
Storage/runtime
  location:      Models, converted artefacts, caches, environments and private
                 reports remain beneath operator-configured private roots
                 outside Git. Executable code uses SAHAY_MODELS_ROOT and has
                 no machine-specific default.
Fallback or
  migration
  action:        Missing CUDA or model artefacts produce an explicit
                 unavailable/degraded result. CPU fallback is permitted and
                 must be labelled degraded. The deterministic pipeline remains
                 authoritative. No model weights, audio, transcripts or
                 private reports may be committed.
Decision maker:  Advay Sinha, acting as Project Owner, Integration Lead and
                 AI/ML Lead, 2026-09-11.
```

```text
Date:            2026-09-12
ID and exact
  version/release:
                 EXT-119 — Local external-corpus training, MuRIL domain
                 adaptation, fictional SAHAY supervision and shadow-MVP
                 qualification using the Task 5 and Task 6 assets already
                 present beneath the operator-controlled private roots.
Decision:        APPROVED
Scope:           Authorizes local, offline experimental training using every
                 usable privacy-processed text record produced by Task 5:
                 Reddit Suicide Detection, Dreaddit, EmoInHindi, the local
                 Hinglish hate-speech derivative and the Hinglish sentiment
                 dataset. Blank rows, unreadable bytes and missing Git LFS
                 media must be counted and reported but must not be invented
                 into usable inputs. CREMA-D remains unavailable because the
                 local media files are Git LFS placeholders.

                 The approved training design has three separate stages:
                 (A) MuRIL domain-adaptive masked-language-model training on
                 all usable processed external text; (B) optional
                 source-specific auxiliary heads whose labels remain in
                 dataset namespaces; and (C) a SAHAY multi-label shadow head
                 trained only on private fictional development examples.

                 External source labels must not be converted automatically
                 into SAHAY crisis, danger, threat, vulnerability, routing,
                 diagnosis, SVI, band, D4 or safe/no-alert labels. In
                 particular, subreddit membership, stress, emotion,
                 sentiment and hate-speech labels are not SAHAY safety ground
                 truth. The existing source-label firewall remains enforced.

                 Authorizes a local ML-owned MVP demonstration for typed
                 fictional text and generated or explicitly approved private
                 audio. Voice processing must use the Task 6 sequence:
                 Silero VAD, validated speech intervals, Whisper Small,
                 deterministic assessment and experimental MuRIL shadow
                 output. GatedTranscriber remains the only approved
                 application entry point, and Whisper must be skipped when no
                 speech is detected.

                 The deterministic crisis pre-check and heuristic pipeline
                 remain authoritative. Shadow-model outputs may be displayed
                 side by side for local development but may not independently
                 change routing, escalation, SVI, D4, evidence links,
                 guardrails or victim-facing wording.

                 Training inputs, generated fictional records, checkpoints,
                 optimizer state, predictions, transcripts and reports must
                 remain beneath explicit private roots outside Git. Training,
                 reload, evaluation and the local demonstration must operate
                 offline after approved assets are present.

                 This approval does not authorize backend, frontend or mobile
                 integration; deployment to victims; a public listener;
                 uploading data; publishing or redistributing datasets or
                 trained weights; commercial use; official, independent,
                 blind or locked evaluation; or claims of clinical validity,
                 production accuracy or safety certification.
Reason:          The local MVP requires a functioning multilingual model, and
                 the Task 5 processed corpora are the available foundation
                 for English, Hindi and Hinglish domain adaptation. Keeping
                 external labels source-specific avoids falsely treating
                 stress, emotion, subreddit origin, sentiment or hate speech
                 as SAHAY risk labels. Fictional SAHAY-labelled supervision
                 supplies the separate development-only safety head. Shadow
                 operation allows the model to be demonstrated and compared
                 without replacing the deterministic safety controls.
Licence/cost
  confirmed:     No new paid service, gated repository or dataset download is
                 approved. Dataset licensing and privacy approval remain
                 unresolved, and local processing does not make those issues
                 disappear. The datasets stay `licence_pending` and
                 `quarantined_research_artifact`; no redistribution,
                 publication, commercial permission or ownership claim is
                 recorded. This is a project-owner risk acceptance for a
                 private local hackathon experiment only.
Storage/runtime
  location:      Existing Task 5 processed inputs beneath
                 `SAHAY_DATASETS_ROOT`; pinned Task 6 models beneath
                 `SAHAY_MODELS_ROOT`; generated corpora, training state,
                 checkpoints and reports beneath `SAHAY_TRAINING_ROOT`.
                 Executable code must have no machine-specific default and
                 must refuse private output paths inside a SAHAY checkout.
Fallback or
  migration
  action:        If private inputs, manifests, hashes, model artefacts, GPU
                 capacity or offline guarantees fail verification, training
                 must stop without silently downloading replacements. Missing
                 checkpoints return unavailable, not zero. The deterministic
                 pipeline remains the fallback and authority. If licensing or
                 privacy review later refuses a dataset, its derived private
                 checkpoints must be quarantined and excluded from subsequent
                 use; the deletion or retraining decision must be recorded.
Decision maker:  Advay Sinha, acting as Project Owner, Integration Lead and
                 AI/ML Lead, 2026-09-12.
Invariant 8
  clarification: Externally derived training records and model weights may
                 be used only for private ML research and an
                 operator-controlled local ML demonstration. They must not be
                 shipped, imported, loaded or called by backend, frontend,
                 mobile or another victim-facing MVP component. Any later
                 Task 8 integration of these weights requires a separate
                 explicit decision addressing Invariant 8, licensing, privacy,
                 model behavior and rollback. For this decision, "working MVP"
                 means the ML-owned local CLI demonstration only.
```

```text
Date:            2026-09-13
ID and exact
  version/release:
                 EXT-120 — environment variable
                 PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO (boolean, default false)
Decision:        APPROVED
Scope:           Controlled MVP Task 5D-L only. Lets the backend show the eight
                 Task 5C candidate S0/S9/SH/SX texts as PROVISIONAL, UNREVIEWED,
                 local-demo-only, text-only assistant turns (PC-12
                 `audio:"none"`). Settings refuse `true` unless APP_ENV is
                 `development` or `test`; production, demo, local, staging and
                 unknown environments fail validation. `fixed_scripts_ready` and
                 audio readiness stay false. This narrows the EXT-117 exclusion
                 on writing/activating fixed scripts for this flag only; it
                 approves no script, reviewer, audio asset or voice.
Reason:          Local demonstration of the candidate wording without
                 claiming review, approval or audio.
Licence/cost
  confirmed:     No package, download, service, credential or network access.
Storage/runtime
  location:      Local `.env` only; `.env.example` documents it as `false`.
Fallback or
  migration
  action:        Leave it false (the default). The fail-closed behaviour of
                 `FIXED_SCRIPTS_REVIEW.md` then applies unchanged.
Decision maker:  Project Owner acting as Integration Lead, via prompt.txt on
                 2026-09-13.
```
