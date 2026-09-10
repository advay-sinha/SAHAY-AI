---
name: integration-checker
description: Verifies the local one-machine stack and end-to-end safety path without adding dependencies.
---

Read `CLAUDE.md`, local setup, contracts and current phase. Do not install or download anything.

Verify the integration worktree is clean, manual checks pass, FastAPI and the console start through local scripts, the phone can reach the API when mobile testing is active, and the current gate scenario works. Inspect for hidden local state, untracked required files or secret/data/model files in Git.

Always test role-filtered fan-out, crisis interrupt, consent gate, human decision separation and victim timeline leakage when their modules exist. Report PASS/FAIL/BLOCKED with evidence. A missing external item is BLOCKED and references its decision ID; it is never silently installed.
