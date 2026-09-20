---
description: Scaffold the local-first SAHAY-AI monorepo without installing or downloading anything
argument-hint: "[local | ml | backend | frontend | mobile]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Prepare the local codebase

Read `CLAUDE.md`, `docs/LOCAL_SETUP.md`, `docs/plan/PHASES.md`, `docs/contracts/CONTRACTS.md`, `docs/dialogue/STATES.md`, and `docs/EXTERNAL_DECISIONS.md`.

Rules:

1. Inspect existing files and never overwrite implemented work.
2. Create files and dependency manifests, but do not install packages or download models/datasets.
3. Use SQLite/SQLAlchemy, local assessment runner, local retriever and mock LLM.
4. Do not create Docker, PostgreSQL, Redis, pgvector, RQ or CI configuration.
5. Keep pure dialogue, guardrail and SVI modules free of I/O and ML dependencies.
6. Write safety-invariant tests during scaffolding.

Create:

```text
ml/{dialogue,guardrails,svi,asr,tts,acoustics,nlp,eval,tests}
backend/app/{models,schemas,api,ws,workers,adapters,services,core}
backend/{alembic,tests,seed}
frontend/src/{api,types,pages,components,mocks}
mobile/src/{screens,audio,net,i18n,components}
data-scripts/
scripts/
runtime/{db,audio,logs,cache,policy-index}/
```

Copy the relevant `.claude/templates/*.CLAUDE.md` into each team directory as `CLAUDE.md`.

Required initial files:

- pinned `backend/requirements.txt`, `ml/requirements.txt`, `frontend/package.json`, `mobile/package.json`
- FastAPI health endpoint
- SQLite configuration and first Alembic migration skeleton
- role-filtered fan-out skeleton plus `backend/tests/test_role_fanout.py`
- consent-gate and victim-timeline leakage tests
- complete pure SVI engine and tests
- dialogue state enum, policy skeleton and crisis interrupt test
- guardrail validator skeleton and prohibition tests
- typed WebSocket contract mirror
- Hindi and English locale files
- dataset manifest/registry headers
- PowerShell start/reset/verify scripts

Before writing dependency versions, present the full proposed dependency list using the external-dependency protocol. Writing or installing unapproved packages is not allowed. If approval is absent, create TODO manifests without invented versions and continue with standard-library scaffolding.

Finish by reporting created/skipped files, outstanding external decisions, manual verification status and the next gate. Do not install or download anything.
