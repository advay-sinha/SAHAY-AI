# Team Operations — One-Machine MVP

## Ownership

Four leads (D-11, lead decision 2026-09-11). They approve every contract and dialogue change together:

| Lead | Owns |
|---|---|
| AI/ML and Safety | `ml/`, `data-scripts/`, safety invariants, guardrails, SVI |
| Backend | `backend/`, `scripts/`, the event allowlist |
| Executive Web | `frontend/` (the executive console) |
| Mobile / Victim Experience | `mobile/` (the victim app) |

- Integration owner: merges into `dev` and resets the demo.
- All four leads: `docs/contracts/`, `docs/dialogue/`, safety rules and the shared Claude setup (`CLAUDE.md`, `.claude/`).
- GitHub usernames for the four roles are **not yet recorded**. `.github/CODEOWNERS` holds explicit `@TODO-...` placeholders until each lead's username is filled in.

## Daily rhythm

- Start: report merged work, current task and blockers.
- Midday: merge stable branches and run `/verify-local`.
- Evening from Day 5: run one complete session on the demo laptop and physical phone.
- Any failure in crisis interrupt, assessment isolation or consent stops feature work until fixed.

## Integration

Use separate worktrees when work is concurrent. The integration owner merges into `dev`, runs manual checks, and promotes a known-good commit to `main` at passed gates. CI/CD is deferred; manual evidence is recorded in the gate report.

## Communication

A blocked external dependency is reported with its decision ID. No team silently installs a substitute. Contract conflicts are resolved in the contract document before implementation.
