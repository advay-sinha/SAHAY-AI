---
description: Daily standup — what changed, what's in flight, what's blocking, measured against the current phase
allowed-tools: Read, Bash, Glob, Grep
---

# Standup

1. **Where we are:** current day and phase from `docs/plan/PHASES.md`; days remaining to the next gate.
2. **What landed:** `git log --oneline` since yesterday, grouped by team prefix (ai / be / fe / infra).
3. **In flight:** open branches and draft PRs, with age. Flag anything older than 48 hours — feature branches are meant to be short.
4. **Verification:** did the latest local manual checks pass on `dev`?
5. **Gate risk:** run a light version of `/gate-check` for the next gate. Name the criteria that are not yet satisfiable and who owns each.
6. **Blocking:** anything waiting on a user decision — pending external dependencies (STOP RULE 2.1), unwritten dialogue scripts, unrecorded scenario audio.
7. **The honest line:** one sentence on whether the next gate is on track. If it is not, say so and name the single biggest cause.

Keep it under 30 lines. No praise, no filler.
