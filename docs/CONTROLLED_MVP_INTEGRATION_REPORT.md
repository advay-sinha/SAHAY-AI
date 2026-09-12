# Controlled MVP integration report

Date: 2026-09-12

Branch: `integration/controlled-mvp`

## Stopping state

The 52-path controlled text MVP was preserved first in local checkpoint commit `ec10d50` (`feat(integration): add controlled text MVP session and handoff`). Nothing was pushed.

The updated `origin/dev` at `61689fa` is now merged with `--no-commit --no-ff`. `MERGE_HEAD` remains `61689fa88aa617c5d3490fc1e0a489987226f6d5`; all resolutions and integration fixes are staged, and the final merge commit has deliberately not been created.

This remains a supervised internal demonstration using fictional data. It is not production-ready, clinically validated, approved for real victims, or an autonomous emergency-response system.

## Incoming dev audit

`cdae3b6..origin/dev` contains `a4507fe` and merge commit `61689fa`. The incoming change modifies 19 paths with 717 insertions and 89 deletions. It adds:

- SQLAlchemy URL normalization for encrypted PostgreSQL through `asyncpg`;
- bounded pooling, pre-ping, connection and command timeouts;
- separate runtime and migration database URLs;
- sanitized configuration, migration and seed failures;
- backend-only PostgreSQL RLS and privilege revocation;
- guarded remote-demo seeding;
- PostgreSQL metadata/configuration tests and SQLite migration compatibility tests;
- the pinned `asyncpg==0.31.0` dependency and setup documentation.

FastAPI remains the only database gateway. Web and Mobile contain no PostgreSQL, Supabase, database URL or database credential integration.

## Conflicts and semantic resolutions

Git reported one textual conflict in `backend/tests/test_legacy_migration.py`. Both branches extended the same migration test with different head IDs. The resolution retains upstream's historical-row assertions, retains PC-11 upgrade/downgrade coverage, uses the shared disposable SQLite environment helper, and expects the new merged head.

The following semantic overlaps were also reconciled:

- Upstream's two-head graph (`2d6e3f4a5b6c` and `9c7e2d4a11b0`) is joined by new forward-only revision `e4b7f8a9c012` without rewriting either branch revision.
- The merge revision applies upstream's backend-only PostgreSQL posture to the PC-11 `human_requests` table.
- Explicit SQLite URLs are accepted for `development`, `local` and `test`; `demo` and `production` still require encrypted PostgreSQL. `DATABASE_URL` remains required, so there is no silent fallback.
- Reset and scenario commands set both `DATABASE_URL` and `MIGRATION_DATABASE_URL`, preventing an ignored `.env` from redirecting Alembic to another database.
- `/health` reports database `configured`, not `ready`; it remains a liveness/configuration endpoint and does not probe database readiness.
- `docs/LOCAL_SETUP.md` now documents the implemented first-frame WebSocket protocol, causal acknowledgements, REST recovery, no replay, local SQLite, backend-only Supabase, and commands that migrate and seed one physical SQLite file.

## Final Alembic graph

Exactly one head exists:

```text
db1fbb96898f
  -> 4abeb4233bf7
    -> 7fbad9360da7
      -> 2d6e3f4a5b6c ----\
      -> 9c7e2d4a11b0 -----+-> e4b7f8a9c012 (head)
```

Revision `9c7e2d4a11b0` remains the controlled-MVP migration for nullable historical `turns.client_message_id`, uniqueness on `(session_id, client_message_id)`, the `human_requests` table, and uniqueness on `(session_id, request_id)`. Historical and system turns remain valid because the new turn identifier is nullable. No published `origin/dev` migration was rewritten by the resolution.

Fresh base-to-head migration, representative existing-database migration, downgrade to `7fbad9360da7`, re-upgrade, uniqueness behavior and `alembic check` pass on disposable SQLite databases.

PostgreSQL verification covers URL normalization, TLS enforcement, pool/timeout options, sanitized errors, model metadata compilation for all 16 tables, security-table coverage, remote-seed boundaries, and the pinned `asyncpg 0.31.0` runtime import. No real Supabase project was contacted or migrated.

Alembic offline PostgreSQL SQL generation cannot pass the published `7fbad9360da7` data-copy revision: that revision fetches existing rows, while an offline Alembic connection returns no result object. Fixing that would rewrite published history, which this integration forbids. Live PostgreSQL upgrade verification therefore requires a separately authorized disposable PostgreSQL target.

## Backend, Web and Mobile contract audit

- Backend supports local SQLite and encrypted PostgreSQL, sanitizes connection/configuration errors, keeps credentials server-side, commits chat before `chat.ack`, and commits a human-request row plus `SH` atomically before `human_request.ack`.
- Crisis detection still runs synchronously before policy and model-dependent work. Deterministic invariance tests cover optional model output, silence, absence, timeout, failure and malformed output.
- Web targets FastAPI, validates exact login/queue/case/timeline/audit/action payloads, sends first-frame socket authentication, accepts events only after `auth.ok`, and refetches REST data after reconnect.
- Mobile targets FastAPI through `EXPO_PUBLIC_API_URL`, creates sessions through `POST /sessions`, keeps credentials and identifiers in memory, uses the returned `case_id`, confirms only correlated acknowledgements, reuses identifiers only on explicit retry, and has no automatic resend or persistent queue.
- Neither client places a bearer token in a page or WebSocket URL. No unsupported shadow, diagnostic or D4 product data was added. Text sessions keep D4 structurally unavailable; no D4 value is invented.

## Web defect resolution and Android preview preparation

- The corrupted Web database fallback now renders an em dash. The remaining Web source scan contains no common mojibake markers.
- The console header no longer asserts a static Operational state. It starts at Checking backend, renders Operational only after an exact successful `/health` response with `status: "ok"`, and renders Backend unreachable after a failed or non-ok response. Regression tests cover both failure paths.
- The Mobile `preview` EAS profile explicitly selects `environment: "preview"` while retaining internal distribution and Android APK output.
- The controlled preview compiles `http://127.0.0.1:18000` with explicit preview and loopback opt-ins. A no-dependency local Expo config plugin enables Android release cleartext only for `EAS_BUILD_PROFILE=preview` and writes it false for production.
- Mobile URL validation permits release-build HTTP only for that explicit preview configuration and a loopback hostname. It rejects preview HTTP on private-LAN/public hosts and rejects every production HTTP URL even if development or loopback flags are supplied. HTTPS remains accepted.
- A USB-connected Android phone must run `adb reverse tcp:18000 tcp:8000`; otherwise the APK's `127.0.0.1:18000` points back to the phone rather than reaching FastAPI on laptop port 8000. `docs/LOCAL_SETUP.md` records installation, verification and reconnection steps.
- The USB preview instructions were corrected to bind FastAPI to `127.0.0.1`, prohibit LAN exposure, and invoke the preview build with `npx eas-cli@latest build --platform android --profile preview` rather than requiring a globally installed `eas` command.

## Verification results

| Area | Result |
|---|---|
| Focused database/config/migration/health tests | 39 passed |
| Complete Backend pytest suite | 185 passed; one existing Starlette/AnyIO deprecation warning |
| Backend Ruff | Passed |
| Web typecheck | Passed |
| Web lint | Passed |
| Web tests | 66 passed |
| Web production build | Passed |
| Mobile typecheck | Passed |
| Mobile model-free tests | 126 passed |
| Expo Android manifest introspection | Preview cleartext true; production cleartext false |
| Preview port and documentation consistency | Device loopback 18000 forwards to laptop FastAPI 8000; no stale 8000-to-8000 preview mapping |
| Relevant Backend security tests | 133 passed; one existing Starlette/AnyIO deprecation warning |
| Deterministic ML unittest discovery | 776 passed |
| Deterministic ML pytest discovery | 776 passed; one pytest-asyncio configuration warning |
| Prediction/model/label firewall tests | Passed within both 776-test ML runs |
| Deterministic backend invariance | Passed within the 185-test Backend run |
| SQLite migration graph and `alembic check` | Passed |
| PostgreSQL model/config/security checks | Passed without contacting a server |
| Whitespace | `git diff --cached --check` passed |

The ML suites printed expected refusal-path diagnostics and did not alter any finalized result.

## Local runtime smoke test

One temporary SQLite file was selected explicitly for `DATABASE_URL` and `MIGRATION_DATABASE_URL`. Alembic, seed and two FastAPI starts used that same file. All data was fictional, all local processes were stopped, and the temporary directory was removed.

The smoke test passed:

1. base-to-head migration and `alembic check`;
2. fictional seed and Backend startup;
3. `/health` liveness without a database-readiness claim;
4. Executive login with the exact response shape;
5. Web dashboard HTTP load from a local Vite process;
6. Mobile-format fictional session creation;
7. authenticated timeline retrieval using the returned `case_id`;
8. first-frame victim authentication followed by a correlated accepted chat acknowledgement;
9. Executive REST reload of the persisted turn;
10. duplicate chat acknowledgement with the original opaque turn ID and one stored turn;
11. correlated human-request acknowledgement;
12. authoritative session state `SH`;
13. Backend restart followed by REST and WebSocket recovery from the persisted database;
14. exact tokens and token query parameters absent from URLs and captured Backend/Web logs;
15. honest connection failure after the Backend was stopped.

The smoke used HTTP and protocol clients plus an HTTP-loaded Web bundle. A physical phone and an interactive browser rendering/accessibility pass were not available in this terminal run.

## Security, privacy and ownership scan

The final staged merge scan found no `.env`, `prompt.txt`, database, runtime file, secret/private path, dataset, checkpoint, model weight, media/binary artifact, Mobile credential-persistence API, or file over 5 MB. There are no unstaged or non-ignored untracked files.

Eight secret-rule matches were reviewed. They are the public `.env.example` placeholder, synthetic redaction/configuration fixtures under Backend tests, and documentation placeholders. None is a real credential. No `.env` values were read or exposed.

The staged ownership roots are repository root configuration/documentation, Backend, Web, Mobile, `docs/LOCAL_SETUP.md`, and local scripts. Web/Mobile additions are limited to the approved defect fixes, preview APK configuration, URL/manifest safeguards and tests. No Task 7B branch/checkpoint/private corpus, shadow product integration, D4 measurement, or real victim data is present.

## Exact remaining blockers

1. A live PostgreSQL base-to-head migration and runtime smoke were not run because no authorized disposable PostgreSQL service is available, and the task forbids using a real Supabase project.
2. Offline PostgreSQL SQL generation stops in published revision `7fbad9360da7` because its data migration requires query results; published history was preserved.
3. The remote EAS build, physical-phone install/runtime check and interactive-browser check remain external manual gates; no remote build was invoked from this terminal.
4. The final merge commit is intentionally pending at the requested stopping point.

## Git status and graph

Status after staging this report: branch `integration/controlled-mvp`, `MERGE_HEAD=61689fa88aa617c5d3490fc1e0a489987226f6d5`, 33 staged paths, zero unstaged paths, zero non-ignored untracked paths.

```text
* ec10d50 (HEAD -> integration/controlled-mvp) feat(integration): add controlled text MVP session and handoff
| * 61689fa (origin/dev) Merge pull request #15 from advay-sinha/feat/backend-supabase-postgres
|/|
| * a4507fe (origin/feat/backend-supabase-postgres) feat(backend): migrate runtime persistence to Supabase PostgreSQL
* | cdae3b6 Merge pull request #13 from advay-sinha/feat/web-console
```

No push, PR, deployment, remote EAS build, merge into `dev`, stash change, real Supabase migration, or final merge commit was performed.
