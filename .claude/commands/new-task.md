---
description: Turn a plan item into a branch, checklist and skeleton, with the right team rules loaded
argument-hint: "<team: ai|be|fe|mobile> <task description>"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# New task: $ARGUMENTS

1. **Load context:** root `CLAUDE.md`, the target directory's `CLAUDE.md`, the relevant part of `docs/plan/PHASES.md`, and any contract this touches.
2. **Locate it in the plan.** Which phase and gate criterion does it serve? If it serves none, ask the user whether it should be done at all before the freeze — scope discipline is the point.
3. **Check for a contract or dialogue impact.** Contract → run `/contract-change` first. Dialogue or guardrail → this is `type:dialogue`, needs two reviewers, and `docs/dialogue/STATES.md` changes in the same PR.
4. **Check for external dependencies.** Anything new to install, download, or call? Ask now, in the STOP-RULE format, before writing code that assumes it.
5. **Branch:** `<type>/<team>-<short-description>` off `dev`.
6. **Write the checklist** in the PR description: what changes, how it will be tested, what "done" means per the directory's `CLAUDE.md`.
7. **Skeleton first, then implementation.** Types and tests before behaviour where it is cheap to do so.
8. **Stop and report** before opening a non-draft PR.
