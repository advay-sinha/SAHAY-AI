# Controlled MVP integration report

Date: 2026-09-12

Branch: `integration/controlled-mvp`

Base: `origin/dev` at `cdae3b66caabf3701866330a063ed57dde63191f`

## Scope and status

This is a supervised internal SIH demonstration using fictional data. It is not production-ready, clinically validated, approved for real victims, an official accuracy evaluation, or an autonomous emergency-response system.

The approved text/session/timeline/handoff slice is implemented and verified. Nothing has been committed, pushed, merged into `dev`, deployed, or applied to PostgreSQL/Supabase. Voice, replay, persistent Mobile credentials, offline queues, automatic resend, D4, shadow-model product integration, and deployment remain deferred.

## Dependency setup

- Backend compatibility includes Python 3.12. `backend/.venv` uses Python 3.12 and the repository-pinned development requirements.
- Frontend dependencies were restored with `npm ci` and the existing lockfile.
- No dependency manifest or lockfile changed and no package was added or upgraded.
- `npm ci` reported 10 existing audit findings. No unapproved `audit fix` was run.

## Implemented integration

### Mobile REST and memory-only session

- `EXPO_PUBLIC_API_URL` is required and accepts only valid HTTP(S) origins. Plain HTTP is restricted to local development hosts.
- `POST /sessions` is issued once after an explicit consent decision, is locked while pending, is never automatically retried, and accepts only the exact frozen nine-key response.
- The root provider retains the session, bearer credential, pending IDs, and socket state only in process memory.
- Authenticated timeline retrieval uses only the active session's `case_id`, sends the credential only in the `Authorization` header, validates the exact response, preserves server order and duplicates, clears the whole session on authentication failure, and discards stale responses.
- Chat and handoff UI state changes only on the matching causal acknowledgement; local socket `send()` success is not treated as persistence.

### Executive Web REST and socket validation

- The frozen login response is exactly `{token, role, display_name}`; missing or extra keys fail closed.
- Every successful REST response passes through an endpoint-specific runtime validator. Malformed successful responses become an unavailable/502 client error rather than rendered data.
- Executive socket authentication uses the exact first frame and no URL credential. Domain events are accepted only after a matching non-victim `auth.ok` and exact runtime validation, including nested dimension, structured-case, alert, and escalation data.
- Server ordering is preserved and reconnect recovery uses authoritative REST refetching without event replay or action resend.

### Canonical WebSocket protocol (PC-11)

- First frame within five seconds: exact `auth` with a nonempty bearer token.
- First server response: exact `auth.ok` with path `session_id` and role `victim`, `executive`, or `supervisor`; no snapshot/domain event precedes it.
- Any query component is rejected. Close codes are 4400 protocol, 4401 authentication/expiry, 4403 authorization, and 1011 internal/database failure, always with an empty reason.
- Chat IDs match `^m:[1-9][0-9]{0,15}$`. Exact chat requests carry only ID, text, and `hi|en` language. Only leading/trailing whitespace is removed; canonical text is 1-2000 Unicode characters and language must match the session.
- `chat.ack accepted` is sent only after commit and means only durable victim-turn persistence. Duplicate retries return the original opaque turn ID (maximum 64 characters); conflicting ID reuse is rejected without another insert.
- Human IDs match `^h:[1-9][0-9]{0,15}$`. The human-request row and transition to `SH` commit atomically. `human_request.ack` is causal; `session.status: SH` is only a state event. Internal UTC `requested_at` is never returned to the victim.
- Reconnect performs authentication, receives the current state snapshot, and refetches permitted REST resources. There is no event replay, automatic resend, persistent queue, or background replay.

### Database migration

Revision `9c7e2d4a11b0` (down revision `7fbad9360da7`) adds:

- nullable `turns.client_message_id VARCHAR(18)`;
- unique constraint `uq_turns_session_client_message` on `(session_id, client_message_id)`;
- internal `human_requests(id, session_id, request_id, requested_at)`;
- cascading session foreign key, session index, and unique `uq_human_requests_session_request`.

The migration and ORM are consistent, SQLite-first, and PostgreSQL-compatible. Verification covered empty base-to-head upgrade, a representative existing database upgrade, uniqueness, concurrent duplicates, downgrade to the prior revision, re-upgrade, and `alembic check`. No real database was modified.

## Verification results

| Area | Result |
|---|---|
| Backend | 166 passed; Ruff passed |
| Backend contract/login focused rerun | 66 passed |
| Web | Typecheck passed; lint passed; 64 tests passed; production build passed |
| Mobile | Typecheck passed; 122 tests passed |
| Deterministic ML | 776 tests passed |
| Diff hygiene | `git diff --check` passed |

Backend emitted one pre-existing Starlette/AnyIO deprecation warning. The ML governance tests printed expected refusal-path diagnostics while all 776 assertions passed; no finalized result was touched.

## Fictional end-to-end and failure results

- Fictional session creation returned the exact frozen shape, then victim WebSocket authentication returned `auth.ok` before the current `session.status` snapshot.
- A fictional chat message was trimmed, durably inserted once, acknowledged as `accepted`, and published only after commit. Exact retry returned `duplicate` with the original turn ID. Different content with the same ID returned `id_conflict`; a language mismatch returned `not_permitted`.
- Concurrent identical chat submissions produced exactly one victim turn and one shared turn ID. Concurrent identical human requests produced exactly one request row and one transition side effect.
- A declined-consent fictional session could still request a human. The request row and `SH` transition committed together; retry returned `duplicate` and caused no repeated side effect.
- Query URLs, malformed JSON, binary data, unknown frames, extra/missing keys, and invalid IDs failed with 4400. Timeout, missing/malformed/expired credentials failed with 4401. Wrong-session victim credentials and unauthorized staff actions failed with 4403. Simulated database/internal failure sent no acknowledgement and closed 1011. Tested close reasons were empty.
- Timeline tests preserved authoritative ordering and duplicates and rejected malformed successful responses rather than presenting an empty state.

## Deterministic authority and safety

- The deterministic crisis pre-check and detector remain authoritative; application code imports neither experimental package.
- An invariance matrix covering optional output firing, silence, unavailability, timeout, failure, and malformed output produced byte-for-byte equal authoritative deterministic results.
- The fictional crisis fixture continued to fire the crisis pre-check and route Critical in every case.
- D4 remained structurally unavailable on the text channel with null score and confidence; no value was invented.
- No Task 7B branch, checkpoint, private corpus, predictions, report, or review packet was integrated or staged.

## Security and privacy scan

- No real secret, private key, environment file, database, checkpoint, dataset, binary, build output, cache, or private record is in the integration diff.
- No Mobile credential persistence API is referenced. Mobile credentials and pending actions remain memory-only.
- Product clients do not construct token-bearing WebSocket URLs. Remaining query-token strings are defensive redaction and credential-scrubbing tests or clearly marked historical review text superseded by PC-11.
- No application import of experimental ML/training packages was found.
- No submitted narrative, token, auth frame, transcript, audio, password, or database credential is logged by the changed application paths.
- Expected scan matches were fictional test passwords, a synthetic PostgreSQL redaction fixture, login field names, and the pre-existing Web console session-scoped credential store. None is a credential leak or a Mobile persistence change.
- `docs/EXTERNAL_DECISIONS.md` and EXT-119 are unchanged.

## Known limitations

- `/health` reports configured/static state; it is not evidence that a database connection is reachable. A readiness contract remains future work.
- SQLite remains the controlled local MVP database. PostgreSQL/Supabase migration is deferred under EXT-110.
- Reconnect recovery depends on REST refetch; WebSocket event history is not replayed.
- Mobile sessions and pending actions disappear when the process ends by design.
- Voice/audio transport, VAD/Whisper application wiring, ASR/TTS, offline queues, and deployment are not implemented.
- S0, S9, and SX fixed scripts remain unavailable as recorded by the existing health/configuration state. Crisis routing remains deterministic and fail-closed, but this is not a victim-ready crisis experience.
- The repository dependency install reported 10 existing npm audit findings; remediation requires separate dependency approval.

## Changed/staged integration paths

Only approved Backend API/schema/model/service/WebSocket/migration/tests, canonical contract documentation, Web API/auth/socket/types/tests, Mobile routes/network/session/screens/types/tests, and this report are staged. `prompt.txt` is ignored by repository policy and was cleared locally after this report was produced, so it is not in the index. Dependency manifests, lockfiles, external decisions, ML research paths, artifacts, databases, and build output are excluded.

Proposed commit message (not executed):

`feat(integration): add controlled text MVP session and handoff`
