# Local Development and Demo Setup

## Current prerequisites

Install now only after approval:

- Git
- Python 3.11
- Node.js 24 LTS and npm
- VS Code or another editor
- a physical Android phone and Android SDK Platform Tools (ADB) for the USB preview gate

FFmpeg, the full Android SDK/Android Studio, Docker and Redis are intentionally deferred until their features need them. The backend supports local SQLite and an explicitly configured Supabase PostgreSQL development/demo project.

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

## Physical Android preview APK over USB

mobile/eas.json defines the controlled local-demo build as the preview profile: named EAS environment preview, internal distribution and Android APK output. That profile compiles EXPO_PUBLIC_API_URL=http://127.0.0.1:18000 plus explicit preview/loopback flags. A repository-local Expo config plugin enables Android cleartext traffic only when EAS_BUILD_PROFILE=preview; production writes usesCleartextTraffic=false.

The application validator independently permits plain HTTP in a non-development build only when the compiled environment is exactly preview, the loopback opt-in is exactly true, and the host is localhost, 127.0.0.1 or ::1. Preview URLs on a LAN or public host and every production HTTP URL fail closed. HTTPS remains valid.

Build and install the controlled preview APK using the existing EAS project and an authorized USB-debugging phone:

~~~powershell
Push-Location mobile
npx eas-cli@latest build --platform android --profile preview
Pop-Location

adb devices
adb install -r <path-to-downloaded-preview.apk>
adb reverse tcp:18000 tcp:8000
adb reverse --list
.\scripts\start-backend.ps1
~~~

Inside the installed APK, 127.0.0.1 is the Android device itself. The adb reverse mapping is therefore required to carry both HTTP and WebSocket traffic on device port 18000 to FastAPI on laptop port 8000. Re-run adb reverse tcp:18000 tcp:8000 after unplugging the cable, revoking USB debugging, restarting ADB or rebooting the phone. This controlled release preview deliberately has no plain-HTTP LAN fallback.

For the controlled USB preview, bind FastAPI to 127.0.0.1 on port 8000. The APK uses http://127.0.0.1:18000, and `adb reverse tcp:18000 tcp:8000` forwards that device port to the laptop backend. Do not expose the backend over LAN.

## Environments

Use separate virtual environments:

```text
backend/.venv/
ml/.venv/
```

Frontend and mobile have independent `package.json` and lockfiles. Never install project packages globally.

## Backend persistence

The backend uses SQLAlchemy with either local SQLite or Supabase PostgreSQL. FastAPI is the only application database gateway; Web and Mobile never receive a Supabase key or database credential and never connect to Supabase directly.

For local development, copy `.env.example` to the ignored `.env` and set:

```dotenv
APP_ENV=development
DATABASE_URL=sqlite+aiosqlite:///./runtime/db/sahay.db
MIGRATION_DATABASE_URL=
```

Relative SQLite paths resolve from the repository root, even when commands run from `backend/`. SQLite enables foreign keys, WAL and a busy timeout. `development`, `local` and `test` accept an explicitly configured SQLite URL; `demo` and `production` require PostgreSQL.

For Supabase, obtain connection strings from the dashboard's Connect panel. Use a direct connection for a persistent backend with IPv6 access. On an IPv4-only development machine, use the Session pooler on port 5432. Do not use transaction pooling on port 6543: it has different prepared-statement and session semantics and is rejected by configuration.

`DATABASE_URL` is the runtime connection. Set `MIGRATION_DATABASE_URL` to a separate direct, migration-safe connection when available. Both must require TLS. Never place either value in source, documentation, shell history, client configuration or test output.

There is no implicit database fallback: `DATABASE_URL` is required. Tests and migration checks use disposable SQLite databases and override both database URL variables so a private `.env` cannot redirect them.

Run migrations and the fictional seed from `backend/`. Both commands below resolve `./runtime/db/sahay.db` to the same physical repository-level file:

```powershell
Push-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic check
$env:SEED_PASSWORD = "<choose a local-only password>"
.venv\Scripts\python.exe seed\seed.py
Pop-Location
```

Before the first Supabase migration, perform the read-only preflight and obtain explicit authorization for the sanitized empty development/demo target. Existing SQLite data is never transferred automatically.

## Console authentication (local MVP)

Contract: `POST /auth/login → {token, role, display_name}` (HANDOVER.md §12.4), Bearer-token JWT. Executive and Supervisor roles (EC-01). No cookies, no SSO/MFA — production authentication is out of MVP scope (HANDOVER.md §8).

**Local-development accounts only.** `backend/seed/seed.py` creates `exec1`, `exec2` (executive) and `sup1` (supervisor). The password comes from `SEED_PASSWORD` in your environment, or is generated and printed once. No credential is committed, compiled into the frontend, or prefilled on the login page. Never reuse these accounts or passwords with real case data. Remote seeding is denied by default and must not be run until schema verification and separate authorization are complete.

**Token transport.**

- REST: `Authorization: Bearer <jwt>` only. A `?token=` query parameter on a REST route is ignored (401).
- Page URLs never carry a token. `/login?token=…` authenticates nothing; the login page strips any query string from the address bar without reading it.
- WebSocket URLs contain only `/ws/session/{session_id}`. Any query component is rejected.
- Within five seconds of opening the socket, the client sends exactly `{"type":"auth","token":"<token>"}`. The server sends no domain event or snapshot before authentication.
- Successful authentication returns `auth.ok` with the path session ID and authenticated role. Only then may the client accept events or send actions.

**Acknowledgements and reconnect recovery.**

- A chat message is shown as confirmed only after its correlated `chat.ack` reports `accepted` or `duplicate`. Socket send success alone is not confirmation.
- A human request is shown as confirmed only after its correlated `human_request.ack`. A `session.status` event is not the causal acknowledgement.
- There is no automatic resend, persistent Mobile queue or WebSocket event replay. An explicit retry reuses the original in-memory identifier.
- After reconnect, authenticate again, wait for `auth.ok`, accept the current state snapshot, and reload authoritative permitted data through REST. Opaque server turn IDs reconcile duplicate transcript lines.

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

Until CI is approved, run focused tests, lint and builds through `scripts/verify-local.ps1`. A designated integration owner runs the complete scenario on the demo machine before merging local team branches. `/health` is a liveness and configuration response; it does not probe the database and must not be used as readiness evidence.

## Database recovery boundary

Alembic creates schema; it does not copy the old SQLite file. Preserve existing SQLite files and sidecars unchanged. Do not reset, truncate or clean a Supabase target. If preflight finds an application table, migration revision or unexpected data, stop and select a newly confirmed empty development/demo project. The security migration's downgrade intentionally does not restore broad client grants or disable RLS.

## Team isolation on one machine

Use separate Git worktrees for AI/ML, backend and frontend/mobile if work happens concurrently. Do not have multiple teams edit one working tree. See `docs/TEAM-OPERATIONS.md`.

## Deferred infrastructure

The previous Docker/CI specification is retained in `docs/deferred/` for later use. Do not activate it automatically.
