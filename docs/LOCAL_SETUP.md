# Local Development and Demo Setup

## Current prerequisites

Install now only after approval:

- Git
- Python 3.11
- Node.js 24 LTS and npm
- VS Code or another editor
- a physical Android phone for the later mobile gate

FFmpeg, Android SDK/ADB, Docker and Redis are intentionally deferred until their features need them. The backend runtime uses an explicitly configured Supabase PostgreSQL development/demo project.

**Node version:** the project targets **Node.js 24 LTS** (24.19.0 installed 2026-09-10). Node 20 is end of life and Node 23 was never an LTS line. Node 22 was the original target, but it has moved to maintenance and is no longer offered by `winget` under `OpenJS.NodeJS.LTS`, which now tracks the active LTS line. `frontend/package.json` and `mobile/package.json` both declare `"engines": { "node": ">=24.0.0 <25.0.0" }`. Recorded as EXT-113 in `docs/EXTERNAL_DECISIONS.md`.

**Python version:** CPython **3.11.9**, installed 2026-09-10 alongside the existing 3.12 and 3.13. Recorded as EXT-114.

## Root layout

Extract this starter so `CLAUDE.md` is at the repository root. Keep datasets and models in a sibling directory:

```text
D:/SAHAY-AI/
├── sahay-ai/
└── sahay-ai-data/
```

Run `/prepare-codebase local` in Claude Code. This is a Claude command, not a PowerShell command.

## Runtime ports

| Process | Port |
|---|---:|
| FastAPI HTTP/WebSocket | 8000 |
| Vite executive console | 5173 |
| Expo Metro | 8081 |

Bind FastAPI to `0.0.0.0` for physical-phone access. The phone uses the laptop's LAN IPv4 address, not `localhost`.

## Environments

Use separate virtual environments:

```text
backend/.venv/
ml/.venv/
```

Frontend and mobile have independent `package.json` and lockfiles. Never install project packages globally.

## Backend persistence

The normal backend runtime is Supabase PostgreSQL through SQLAlchemy and the asynchronous PostgreSQL driver. FastAPI remains the only application database gateway; web and mobile clients receive no Supabase key or database credential.

Copy `.env.example` to the ignored `.env` and obtain connection strings from the Supabase dashboard's Connect panel. Use a direct connection for a persistent backend with IPv6 access. On an IPv4-only development machine, use the Session pooler on port 5432. Do not use transaction pooling on port 6543: it has different prepared-statement and session semantics and is rejected by configuration.

`DATABASE_URL` is the runtime connection. Set `MIGRATION_DATABASE_URL` to a separate direct, migration-safe connection when available. Both must require TLS. Never place either value in source, documentation, shell history, client configuration or test output.

Normal startup has no SQLite fallback. Disposable SQLite remains available only when `APP_ENV=test` for unit/integration tests, migration compatibility checks and the guarded local scenario/reset scripts.

Run migrations from `backend/`:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic check
```

Before the first Supabase migration, perform the read-only preflight and obtain explicit authorization for the sanitized empty development/demo target. Existing SQLite data is never transferred automatically.

## Console authentication (local MVP)

Contract: `POST /auth/login → {token, role}` (HANDOVER.md §12.4), Bearer-token JWT. Executive and Supervisor roles (EC-01). No cookies, no SSO/MFA — production authentication is out of MVP scope (HANDOVER.md §8).

**Local-development accounts only.** `backend/seed/seed.py` creates `exec1`, `exec2` (executive) and `sup1` (supervisor). The password comes from `SEED_PASSWORD` in your environment, or is generated and printed once. No credential is committed, compiled into the frontend, or prefilled on the login page. Never reuse these accounts or passwords with real case data. Remote seeding is denied by default and must not be run until schema verification and separate authorization are complete.

```powershell
$env:SEED_PASSWORD = "<choose a local-only password>"
backend\.venv\Scripts\python.exe backend\seed\seed.py
```

**Token transport.**

- REST: `Authorization: Bearer <jwt>` only. A `?token=` query parameter on a REST route is ignored (401).
- Page URLs never carry a token. `/login?token=…` authenticates nothing; the login page strips any query string from the address bar without reading it.
- WebSocket: the frozen contract puts the token in the handshake URL, `WSS /ws/session/{id}?token=<jwt>`, because a browser WebSocket cannot send an Authorization header. That URL is not a page URL and never enters browser history, but uvicorn logs it, so `backend/app/core/log_redaction.py` rewrites `token=` values and anything JWT-shaped to `[REDACTED]` in every uvicorn log line.
- **PC-05 (approved in principle, phased, 2026-09-11):** the target protocol moves the socket token out of the URL into a first `{"type":"auth","token":...}` frame, with a short timeout and no data before authentication (CONTRACTS.md §1). Backend and Executive Web own the implementation. Until it ships, the query-token form above stays supported for the text-first web slice. `POST /sessions` already returns `ws_url` without a token and the victim credential as `session_token` (PC-09); clients append `?token=` themselves.

**Session storage.** The project had no existing session mechanism, so the console keeps `{token, role, displayName, expiresAt}` in `sessionStorage` under `sahay.console.session`: it survives a reload, ends with the tab, and is not shared between tabs. If storage is blocked, it falls back to memory. Trade-off: any script on the page can read `sessionStorage`, so the console loads no third-party scripts or CDN assets and renders no raw HTML.

**Session lifecycle.**

| Event | Result |
|---|---|
| Login succeeds | Response shape and role validated; token's own `role` must match; stored; executive → `/queue`, supervisor → `/supervisor` |
| Login fails | Fixed message; nothing stored. Unknown user and wrong password are indistinguishable (same 401 body, same Argon2 work) |
| Any API 401 | Session cleared, back to `/login` |
| Token expired, malformed or tampered in storage | Deleted on the next read; treated as signed out |
| Sign out | Session cleared, back to `/login` |
| Signed-in user opens `/login` | Redirected to their home |
| Executive opens `/supervisor` | Redirected to `/queue`; supervisor navigation is not rendered |

UI role checks are navigation only. The backend checks the token and role on every protected request (`backend/app/core/auth.py`): 401 for a missing, malformed, forged, expired or claim-less token; 403 for a valid token with the wrong role. Supervisor-only endpoints are BE-021 (P3) and will use `require_supervisor`.

**Known limitation.** Logout is client-side. JWTs are stateless, so a copied token stays valid until it expires (`JWT_EXPIRY_MINUTES`, default 480). Server-side revocation is not implemented in the MVP.

## Manual verification

Until CI is approved, run focused tests, lint and builds through `scripts/verify-local.ps1`. A designated integration owner runs the complete scenario on the demo machine before merging local team branches.

## Database recovery boundary

Alembic creates schema; it does not copy the old SQLite file. Preserve existing SQLite files and sidecars unchanged. Do not reset, truncate or clean a Supabase target. If preflight finds an application table, migration revision or unexpected data, stop and select a newly confirmed empty development/demo project. The security migration's downgrade intentionally does not restore broad client grants or disable RLS.

## Team isolation on one machine

Use separate Git worktrees for AI/ML, backend and frontend/mobile if work happens concurrently. Do not have multiple teams edit one working tree. See `docs/TEAM-OPERATIONS.md`.

## Deferred infrastructure

The previous Docker/CI specification is retained in `docs/deferred/` for later use. Do not activate it automatically.
