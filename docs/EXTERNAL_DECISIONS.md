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
