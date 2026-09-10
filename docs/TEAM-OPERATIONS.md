# Team Operations — One-Machine MVP

## Ownership

- AI/ML: `ml/`, `data-scripts/`
- Backend: `backend/`
- Frontend/Mobile: `frontend/`, `mobile/`
- Integration owner: `scripts/`, merges and demo reset
- All leads: contracts, dialogue states and safety rules

## Daily rhythm

- Start: report merged work, current task and blockers.
- Midday: merge stable branches and run `/verify-local`.
- Evening from Day 5: run one complete session on the demo laptop and physical phone.
- Any failure in crisis interrupt, assessment isolation or consent stops feature work until fixed.

## Integration

Use separate worktrees when work is concurrent. The integration owner merges into `dev`, runs manual checks, and promotes a known-good commit to `main` at passed gates. CI/CD is deferred; manual evidence is recorded in the gate report.

## Communication

A blocked external dependency is reported with its decision ID. No team silently installs a substitute. Contract conflicts are resolved in the contract document before implementation.
