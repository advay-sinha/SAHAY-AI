# Local scripts

These scripts never install packages or download external files. They use dependencies only after those dependencies have been approved and installed.

- `check-prerequisites.ps1` — read-only presence/version checks.
- `start-backend.ps1` — starts FastAPI from `backend/.venv`.
- `start-frontend.ps1` — starts Vite from installed dependencies.
- `start-mobile.ps1` — starts Expo from installed dependencies.
- `verify-local.ps1` — runs the verification gate in two tiers. Every Python
  check uses the component virtual environments: `backend/.venv` for backend
  checks and `ml/.venv` for the ML suite. There is no fallback to a bare system
  Python; if either venv is missing the script stops before any check with a
  setup instruction (exit 2). Tier 2 reports `BLOCKED` if `node_modules` is
  missing, and a `BLOCKED` or `FAIL` result makes the gate exit non-zero. The
  backend's pinned Ruff lints both `backend/` and `ml/`, because
  `ml/requirements-dev.txt` carries no linter.
- `reset-db.ps1` — a test/demo utility that deletes only a guarded local SQLite
  file and reseeds deterministically. It never targets PostgreSQL. Prompts for
  confirmation. Requires the approved backend dependencies.

## What runs with nothing installed

These manual commands exercise the standard-library modules without any venv.
They are a quick smoke check, not the gate: backend tests that need the pinned
packages skip or fail under a bare interpreter, so `verify-local.ps1` runs them
in the component venvs instead.

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
