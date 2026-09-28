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
| EXT-002 | Mozilla Common Voice Hindi | One named release; selected Hindi evaluation splits | ASR WER/CER | APPROVED | 2026-09-24 | Project owner | Release is chosen at M11; the owner downloads it (the portal may need a login). See the 2026-09-24 batch entry. |
| EXT-003 | RAVDESS | Audio_Speech_Actors_01-24.zip only | SER training and evaluation (M12) | APPROVED | 2026-09-24 | Project owner | 208,468,073 bytes, md5 `bc696df654c87fed845eb13823edef8a`, CC BY-NC-SA 4.0 |
| EXT-004 | faster-whisper | small model; CPU int8 local use | ASR | APPROVED via EXT-118 | 2026-09-11 | Project owner | Superseded by EXT-118 (pinned Whisper Small, CT2 FP16 with a CPU int8 fallback) |
| EXT-005 | Silero VAD | One pinned model/release | Endpointing | APPROVED via EXT-118 | 2026-09-11 | Project owner | Superseded by EXT-118 (silero-vad 6.2.1) |
| EXT-113 | Node.js runtime target | Node.js 24.19.0 LTS; `engines` >=24 <25 | Frontend and mobile toolchain | APPROVED (amended) | 2026-09-10 | Project owner | Amended from Node 22: winget no longer offers 22 under OpenJS.NodeJS.LTS |
| EXT-114 | CPython 3.11.9 (Windows x64) | Interpreter only, alongside existing 3.12 and 3.13.2 | backend/.venv and ml/.venv | APPROVED (installed) | 2026-09-10 | Project owner | Installed 2026-09-10; 3.12/3.13 untouched |

## Deferred decisions

| ID | Item | Status | Earliest phase |
|---|---|---|---|
| EXT-101 | FFmpeg | PROPOSED | When audio conversion is implemented |
| EXT-102 | Android SDK/ADB | PROPOSED | When physical-phone testing starts |
| EXT-103 | TTS model/voice | APPROVED 2026-09-24 (scope in batch entry) | M13 |
| EXT-104 | CREMA-D | APPROVED 2026-09-24: `AudioWAV` only | M12 |
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
Date:            2026-09-24
ID:              EXT-128 (D-15) — read-only metadata lookups
Decision:        APPROVED and performed 2026-09-24
Scope:           HTTP GET of public metadata only: Hugging Face model and
                 dataset API and model cards, the PyPI JSON for funasr, the
                 Zenodo record API for RAVDESS, GitHub raw licence and README
                 files, and HEAD requests for the GoEmotions TSVs. No model,
                 dataset or package file was downloaded.
Findings:        Recorded in the entries below. Two corrections to the plan:
                 (1) WavLM Base+ is CC BY-SA 3.0 (the UniSpeech licence linked
                 from its model card), not MIT; (2) emotion2vec+ large ships a
                 single 1.95 GB model.pt under the FunASR Model Open Source
                 License v1.1, and its fine-tuning data list is unpublished
                 ("details of data engineering will be announced later").
Decision maker:  Project owner, 2026-09-24.
```

```text
Date:            2026-09-24
ID and exact
  version/release:
                 Batch approval of plan decisions D-1 to D-14
                 (docs/plan/ML_NATIONAL_MVP.md, section 5). The project owner
                 approved every listed decision on 2026-09-24.

EXT-003 (D-5a)   RAVDESS, Zenodo record 1188976 (v1.0.0, doi
                 10.5281/zenodo.1188976), file Audio_Speech_Actors_01-24.zip
                 only: 208,468,073 bytes, md5 bc696df654c87fed845eb13823edef8a.
                 Licence CC BY-NC-SA 4.0 (non-commercial, share-alike,
                 attribution). Scope: local SER training and evaluation.
EXT-104 (D-5b)   CREMA-D AudioWAV/ only, fetched by `git lfs pull --include
                 "AudioWAV/*"` into the existing local clone: 7,442 files,
                 577.8 MB, sha256 per file taken from the local LFS pointers.
                 Licence ODbL 1.0. A mirror is allowed only if every file
                 matches its pointer sha256. AudioMP3 and VideoFlash are
                 excluded.
EXT-121 (D-4)    numpy 2.5.3 and torchaudio 2.11.0+cu128 (EXT-118 pins) may be
                 used for prosody and D4 features: resample,
                 detect_pitch_frequency, energy, and pause and rate measures.
                 No new package.
EXT-122 (D-7)    The pinned Whisper Small upstream weights (EXT-118,
                 model.safetensors sha256 1d773488…) may be loaded frozen as an
                 SER feature extractor, a challenger only. It does not
                 transcribe on this path.
EXT-123 (D-9a)   Text-affect training in shadow: fine-tuning MuRIL (Stage A
                 init plus a base-MuRIL ablation) and XLM-R base (extending
                 EXT-118's comparison-only scope) on EmoInHindi mapped to
                 affect:neutral|happy|sad|angry|fearful, a deterministic
                 Roman-script transliterated copy, and GoEmotions (EXT-125).
                 Outputs stay private and are shown only in the local ML demo.
EXT-124 (D-10)   microsoft/wavlm-base-plus at revision
                 4c66d4806a428f2e922ccfa1a962776e232d487b: pytorch_model.bin
                 377,617,425 bytes, sha256 3bb273a6ace99408b50cfc81afdbb7ef
                 2de02da2eab0234e18db608ce692fe51, plus config.json and
                 preprocessor_config.json. Licence CC BY-SA 3.0 (corrected;
                 the plan said MIT). Fine-tuned weights are derivatives: keep
                 them private; any redistribution would need to be CC BY-SA.
                 Loaded weights-only, offline.
EXT-125 (D-11)   GoEmotions, google-research/goemotions/data/{train,dev,test}
                 .tsv and emotions.txt (3,519,053 / 439,059 / 436,706 / 248
                 bytes at master on 2026-09-24). The Hugging Face dataset card
                 states Apache-2.0. The raw URLs are not immutable, so sha256
                 is recorded at first fetch and verified afterwards. The
                 comments are public Reddit text: shadow training only.
EXT-126 (D-13)   emotion2vec/emotion2vec_plus_large at revision
                 6c303ba987b86b93193de93e34bb2b077a6bedc4: model.pt
                 1,945,790,254 bytes, sha256 be501a01f26fcdc7663a062dff86af83
                 9afbaef7c4de32f5e42d7e1ad2784da4, plus config.yaml,
                 configuration.json and tokens.txt. Licence: FunASR Model Open
                 Source License v1.1 (use, modification and sharing allowed with
                 attribution and retained model names; "reference and learning
                 purposes"; Alibaba may revise the terms unilaterally). Frozen
                 inference only (zero-shot 9→5 and embeddings). Its fine-tuning
                 data is unpublished and its seed stage used EmoBox, so RAVDESS
                 and CREMA-D results for it are labelled
                 possibly_seen_in_pretraining.
EXT-127 (D-14)   Isolated environment `sahay-ser-e2v` (CPython 3.12,
                 outside Git, beside sahay-ml-models): torch 2.11.0+cu128 plus
                 funasr 1.4.16 (wheel sha256 f95943f6…d08bf450d, MIT) with its
                 resolved dependencies. The exact lock is produced by the
                 owner's `pip freeze` at run R1 and committed as
                 ml/ser/requirements-e2v.lock. It is only for emotion2vec
                 feature extraction, the zero-shot run and ONNX export. The
                 model loads from a local path with disable_update=True and
                 networking blocked; the modelscope hub is never contacted.
                 sahay-ml-models is never modified.
EXT-120 (D-2)    GatedTranscriber (EXT-118) may be integrated behind the
                 backend ASR adapter for whole-utterance upload (VF-11): local
                 only, no public listener.
EXT-002 (D-3)    Common Voice Hindi: one release, evaluation split only, for
                 WER/CER. Plus consented, team-recorded fictional audio.
EXT-103 (D-6)    TTS: human-recorded audio for the approved fixed scripts,
                 plus a built-in offline Windows voice for validated generated
                 turns. No TTS model is downloaded.
D-1              A fourth, regional language is approved in principle. The
                 language is not yet chosen, and it ships only with a fluent
                 human reviewer.
D-8 (lead)       SER → D4 mapping: SER plus text affect is at most 30% of D4
                 (at most 3.6 SVI points). Selection uses the team-dev slice
                 (2 speakers). The promotion gate requires 5-class UAR ≥ 0.45
                 on the team's Hindi and English gate speakers, no class recall
                 below 0.20, and a neutral negative control. Affect never
                 affects the crisis pre-check, routing, overrides or forced
                 bands.
D-9b             Text affect in the product D4 is approved by the owner, but
                 it activates only when all of these hold: (a) the EmoInHindi
                 and GoEmotions licences are confirmed and recorded (EmoInHindi
                 is licence_pending); (b) the text head passes the D-8 gate on
                 human-written E6 data; (c) a config flag defaults to off, as
                 the rollback. Until then it stays shadow-only. This is the
                 separate decision EXT-119's invariant 8 clarification
                 requires, and these conditions are its privacy, licensing,
                 behaviour and rollback terms.
Decision:        APPROVED (as scoped above)
Reason:          Problem Statement 26093 requires speech analytics and emotion
                 AI. The owner requires SER in the national MVP, uses MuRIL
                 where it fits, and keeps text and speech as separate models
                 sized for the RTX 4060 (8 GB) laptop.
Storage/runtime
  location:      Models under SAHAY_MODELS_ROOT, audio and text datasets under
                 SAHAY_DATASETS_ROOT, and features, checkpoints and reports
                 under SAHAY_TRAINING_ROOT. Nothing goes into Git except code,
                 manifests, the lock file and aggregate reports.
Fallback or
  migration
  action:        If emotion2vec hits a deferral trigger (X1–X5 in the plan),
                 WavLM Base+ becomes primary, then the Whisper-encoder head,
                 then prosody only. If a download fails verification, stop:
                 no silent substitution.
Decision maker:  Project owner, 2026-09-24. All downloads and training runs
                 are executed manually by the owner (run points R1–R7).
```

```text
Date:            2026-09-26
ID:              EXT-129 — Dataset use for MVP model training and validation
Decision:        APPROVED (project owner)
Scope:           Every registered and downloaded dataset may be used for MVP model
                 research, training and validation, whatever its registry review
                 status or record-level prohibited uses. This covers the Task 5
                 text corpora (Reddit Suicide Detection, Dreaddit, EmoInHindi,
                 the Hinglish hate-speech derivative, Hinglish sentiment), the SER
                 audio corpora, and datasets added later. Source labels may act as
                 weak-supervision training/validation labels through
                 label_firewall.map_for_training, tagged
                 weak_supervision_from_source_label with their former caveat.
Unchanged:       Registry licence and review fields keep recording the facts
                 (licence_pending stays licence_pending). Still refused: raw
                 dataset text or audio in the product, demo, backend ingestion,
                 fixtures, victim-facing output or Git; the official locked and
                 blind sets and independent/official evaluation; redistribution,
                 publication, commercial use and external upload; learning
                 diagnosis, the SVI, the band, routing or text-derived D4 from a
                 source label; map_to_sahay (official labels). Datasets explicitly
                 marked rejected stay refused. Product integration of trained
                 weights still follows its own gates (D-8, D-9b).
Invariant 8:     Clarified: data from SAHAY's own users is never used. Public
                 research datasets may train and validate MVP models; their content
                 never reaches the product or a victim. Supersedes the stricter
                 reading in the EXT-119 clarification for training and validation.
Reason:          The dataset gates were written for an early, narrower MVP. The
                 national MVP needs the available corpora for model training and
                 validation.
Licence/cost:    Project-owner risk acceptance for the licence_pending datasets,
                 for local, non-commercial hackathon model development only.
Decision maker:  Project owner, 2026-09-26.
```

```text
Date:            2026-09-28
ID:              EXT-129 — implementation note: Stage W weak supervision (no new dependency)
Scope:           ml/data/weak_corpus.py maps three already-downloaded, already-segmented
                 sources through label_firewall.map_for_training, each to one training
                 target with its caveat: Reddit Suicide Detection -> crisis_self_harm,
                 the hate-speech derivative -> continuing_threat, Dreaddit (715-post
                 local copy) -> D5. ml/training/stage_w.py trains shadow-only MuRIL
                 arms W0/W1/W2 on them plus the Task 7B fictional corpus. Nothing is
                 downloaded or installed; no product component loads the weights.
Decision maker:  Project owner, 2026-09-28 (Stage W plan approved, including W2).
```

```text
Date:            2026-09-27
ID:              EXT-120 — implementation note (no new dependency)
Scope:           Backend settings ASR_PROVIDER (mock | local_service; default mock),
                 ASR_SERVICE_URL (http://127.0.0.1 or http://[::1] only; default
                 http://127.0.0.1:8765) and ASR_TIMEOUT_SECONDS, added to .env.example.
                 The ML-owned speech-to-text process (`python -m ml.voice.service`)
                 runs in sahay-ml-models, refuses any non-loopback bind, loads its
                 models with network connections blocked, and uses only EXT-118
                 packages (PyAV decoding through faster-whisper). No package, model or
                 service was added. The upload endpoint stays 501 until the leads
                 confirm contract change PC-11.
Measured:        Warm latency 323–374 ms for a 1.6 s clip on the RTX 4060 (contract
                 budget ≤ 0.6 s); silence returns no_speech in 134 ms without Whisper.
Decision maker:  Project owner, 2026-09-27 (M11 approval).
```
