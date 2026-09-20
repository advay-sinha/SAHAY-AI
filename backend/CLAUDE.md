# Backend Team Instructions

Read root `CLAUDE.md`, contracts, local setup, phase plan and external decision log before editing.

Own FastAPI, SQLAlchemy models, SQLite persistence, REST/WebSocket APIs, consent, auth/RBAC, audit, role-filtered fan-out, local assessment runner, adapters and escalation packet assembly.

## Required architecture

- SQLite through SQLAlchemy/Alembic for the local MVP.
- Normal assessment runs outside the reply path through an interface and local runner.
- Crisis pre-check runs synchronously before dialogue policy.
- Victim sockets receive only the victim-safe event allowlist.
- AI recommendations and human decisions use separate records.
- Override reason is mandatory server-side.
- Timeline responses contain no SVI, band, dimension, alert, emotion or confidence fields.
- LLM, ASR/TTS, storage, assessment runner and retrieval stay behind adapters/mocks.

Do not install packages, add services or download anything without an approved decision. Docker, PostgreSQL, Redis, RQ and pgvector are deferred.

Before completion, run backend tests, including role fan-out, consent gate, crisis path, human-decision separation and timeline leakage. Report blocked checks instead of weakening them.
