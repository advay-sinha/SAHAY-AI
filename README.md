# SAHAY-AI

Local-first AI-assisted intake, vulnerability assessment and human escalation prototype for NHAA 14566, Smart India Hackathon Problem Statement 26093.

## Start here

1. Read `CLAUDE.md`.
2. Read `docs/HANDOVER.md` for the complete specification.
3. Read `docs/LOCAL_SETUP.md`.
4. Review `docs/DATASETS_AND_SERVICES.md` and `docs/EXTERNAL_DECISIONS.md`.
5. Run `/prepare-codebase local` in Claude Code.
6. Run `/setup-status` before installing or downloading anything.

## Current runtime target

- Windows development/demo machine
- CPython 3.11.9 and Node.js 24 LTS
- FastAPI + SQLAlchemy + Supabase PostgreSQL or local SQLite
- local background assessment runner
- React/Vite executive console
- Expo victim app on a physical Android phone
- local self-hosted speech/models
- mock LLM by default
- manual verification

Docker, CI/CD, Redis and pgvector are deferred. SQLite remains supported for local development and tests.

## Checks that run today, with nothing installed

The safety-critical modules are dependency-free on purpose, so their tests run
on a bare interpreter before EXT-001 is decided:

```powershell
python -m unittest discover -s ml/tests -t .        # dialogue, guardrails, SVI, purity
python -m unittest discover -s backend/tests -t .   # role fan-out, consent, timeline leakage
node --test "mobile/tests/*.test.js"                # no assessment data in the victim app
```

`.\scriptserify-local.ps1` runs all three and reports which of the remaining
checks are blocked on approvals.

## Local commands after dependencies are approved and installed

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
.\scripts\start-mobile.ps1
.\scripts\verify-local.ps1
```

Never commit `.env`, databases, audio, datasets, model weights, credentials or real personal data.
