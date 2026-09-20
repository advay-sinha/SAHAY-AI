---
description: Check the current local-first phase gate against executable evidence
allowed-tools: Read, Bash, Glob, Grep
---

# Gate check

Read `CLAUDE.md` and `docs/plan/PHASES.md`. Determine the current phase from repository evidence. Run applicable tests and local health checks without installing or downloading anything.

Every result must be PASS, FAIL or BLOCKED. Cite the command/test evidence. Treat crisis interrupt, role-filtered fan-out, consent and human-decision separation as mandatory. Docker and CI are not current gate requirements. End with the smallest action that will move the gate to PASS.
