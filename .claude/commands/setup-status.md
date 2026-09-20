---
description: Audit local prerequisites, decisions and scaffold readiness without modifying the machine
allowed-tools: Read, Bash, Glob, Grep
---

# Setup status

Read `CLAUDE.md`, `docs/LOCAL_SETUP.md`, `docs/DATASETS_AND_SERVICES.md` and `docs/EXTERNAL_DECISIONS.md`.

Perform read-only checks for Git, Python 3.11, Node 24 LTS, npm, project directories, `.env.example`, dependency manifests and runtime directories. Do not install missing tools. Do not download anything. Do not print secret values.

Report:

1. Present prerequisites.
2. Missing prerequisites and which phase needs them.
3. Approved external items.
4. Proposed/deferred external items.
5. Repository scaffold gaps.
6. The single next action required for the current gate.
