# Contributing to SAHAY-AI

## Local team workflow

The MVP is built on one machine. Use Git even without GitHub CI. If teams work concurrently, use separate worktrees:

```powershell
git checkout dev
git worktree add ..\sahay-ai-ml -b feat/ai-current dev
git worktree add ..\sahay-ai-backend -b feat/be-current dev
git worktree add ..\sahay-ai-frontend -b feat/fe-current dev
```

Each team edits only its owned directories. A designated integration owner merges reviewed branches into `dev` after running manual verification. `main` remains demo-ready.

## Branch and commit naming

Branches: `<type>/<team>-<description>` where type is `feat`, `fix`, `test`, `docs`, `chore` or `refactor`, and team is `ai`, `be`, `fe` or `integration`.

Use Conventional Commits:

```text
feat(svi): add crisis hard override
fix(ws): prevent assessment event fan-out to victim
```

## Reviews

- One reviewer from another team for normal changes.
- All team leads for contract/schema changes.
- Two reviewers for dialogue, crisis and guardrail changes.
- Integration owner runs `scripts/verify-local.ps1` before merging.

## External dependencies

No contributor or Claude instance installs, downloads or adds a service without an approved entry in `docs/EXTERNAL_DECISIONS.md`. Secrets go in the ignored `.env` and are never pasted into documentation, issues or commits.

## Never commit

Secrets, `.env`, audio/video, datasets, databases, model weights, generated media, real personal data, or files over 5 MB. Commit manifests, checksums, scripts and aggregate results.

## Contract changes

Build against `docs/contracts/CONTRACTS.md`. A proposed contract change must state the old shape, new shape, affected teams, migration and safety impact. Record lead agreement before changing code.

## Definition of done

Focused tests and manual checks pass; safety invariant tests pass; external decisions and documentation are current; user-facing work has been checked on the demo machine or physical phone when applicable.
