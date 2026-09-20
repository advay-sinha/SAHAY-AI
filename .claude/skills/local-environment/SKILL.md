---
name: local-environment
description: Prepare, start, inspect or troubleshoot the single-machine SAHAY-AI runtime without Docker.
---

# Local environment

1. Read `docs/LOCAL_SETUP.md` and `docs/EXTERNAL_DECISIONS.md`.
2. Inspect before changing. Missing software is not authorization to install it.
3. Use SQLite, local filesystem, local assessment runner, local retriever and mock LLM.
4. Put runtime files under ignored `runtime/`; put models/datasets under the external `DATA_ROOT`.
5. Never print `.env` contents or secrets.
6. Bind the API to `0.0.0.0` only when phone testing needs LAN access.
7. Keep start/reset/verify operations deterministic and reversible.
8. For every missing package, binary, SDK or service, use the master external-dependency request and wait.
9. Do not introduce Docker, PostgreSQL, Redis, pgvector or CI as a troubleshooting shortcut.
10. Report commands run, observed results and any blocked decision IDs.
