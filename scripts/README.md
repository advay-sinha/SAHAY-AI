# Local scripts

These scripts never install packages or download external files. They use dependencies only after those dependencies have been approved and installed.

- `check-prerequisites.ps1` — read-only presence/version checks.
- `start-backend.ps1` — starts FastAPI from `backend/.venv`.
- `start-frontend.ps1` — starts Vite from installed dependencies.
- `start-mobile.ps1` — starts Expo from installed dependencies.
- `verify-local.ps1` — runs the verification gate in two tiers. Tier 1 needs no
  installed dependency; Tier 2 reports `BLOCKED` if a virtual environment or
  `node_modules` is missing, rather than weakening the check. Nine checks, all
  passing as of 2026-09-10 with EXT-001 installed.
- `reset-db.ps1` — deletes the local SQLite files and reseeds deterministically.
  Prompts for confirmation. Requires EXT-001.

## What runs with nothing installed

```powershell
python -m unittest discover -s ml/tests -t .
python -m unittest discover -s backend/tests -t .
node --test "mobile/tests/*.test.js"
```

The safety-critical modules are standard library only on purpose, so the
guardrails, the dialogue state machine, the SVI engine, the role fan-out, the
victim-app leakage checks and the cross-language contract mirror are all
testable before any approval lands.

`backend/tests/test_contract_mirror.py` is the drift guard: it reads
`docs/contracts/CONTRACTS.md`, `backend/app/ws/events.py`, `ml/svi/dimensions.py`
and `frontend/src/types/contracts.ts` as text and fails if the four disagree on
the event allowlists, the SVI weights, the band thresholds or the abstention
floor. Three hand-maintained copies of one frozen contract will otherwise drift,
and the failure mode is an assessment event reaching a victim client.
