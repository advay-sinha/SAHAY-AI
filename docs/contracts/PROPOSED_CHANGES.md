# Contract changes PC-01 to PC-10 — lead decisions

`CONTRACTS.md` is frozen and changes only with the leads' approval. The items below were proposed on 2026-09-10 while the vertical slice was built. **The leads decided all ten on 2026-09-11**, and the decisions are applied in the same change as `CONTRACTS.md` v2.

| Item | Decision | Status |
|---|---|---|
| PC-01 alert acknowledgement | **APPROVED** | Frozen and implemented. CONTRACTS §4 |
| PC-02 `alert_type` | **APPROVED** | Frozen and implemented. CONTRACTS §3 |
| PC-03 audit-only overrides/timeline | **REJECTED**; dedicated tables instead | Implemented: `overrides`, `timeline_events`. CONTRACTS §6 (15 tables) |
| PC-04 assignment event on the socket | **DEFERRED** (not rejected) | The console keeps polling `/queue` |
| PC-05 socket auth out of the URL | **APPROVED IN PRINCIPLE, phased** | Target frozen. The query token is temporarily supported. CONTRACTS §1 |
| PC-06 supervisor reassignment | **DEFERRED** | The supervisor view is read-only; console writes are executive-only |
| PC-07 officer messaging | **APPROVED WITH STRICT LIMITS** | Frozen and implemented with safety tests. CONTRACTS §2, §4 |
| PC-08 text-channel renormalisation | **APPROVED CONDITIONALLY** | Implemented with boundary, sensitivity, determinism and explanation tests. CONTRACTS §5, §7 |
| PC-09 `POST /sessions` response | **APPROVED AND FROZEN** | Implemented. CONTRACTS §4 |
| PC-10 enumerations and error shape | **FROZEN** (HANDOVER vocabulary) | Implemented; centralised in `backend/app/core/enums.py`. CONTRACTS §9 |

Approvers (D-11): the leads for AI/ML and Safety, Backend, Executive Web, and Mobile/Victim Experience (`.github/CODEOWNERS`, `docs/TEAM-OPERATIONS.md`).

---

## PC-01 — Alert acknowledgement route — **APPROVED**

**Why.** EC-06 (P0) requires every safety alert to be acknowledged. The v1 REST list had no route for it.

**Frozen.**

```
POST /cases/{case_id}/alerts/{alert_id}/ack
  auth   executive only (the supervisor view is read-only, PC-06)
  access the officer must have access to the case: 403 if another officer has claimed it
  body   none
  200    {alert_id, case_id, acknowledged_by, acknowledged_at}
  repeat 200 with the FIRST acknowledgement (idempotent; no duplicate audit event)
  404    alert not on this case
```

- The route records the officer and the time.
- It changes neither the assessment, the band, nor the victim timeline, and it creates no victim timeline action.
- An alert whose severity later escalates is reset to unacknowledged and needs a fresh acknowledgement (audited as `alert.escalated`).

Code: `backend/app/api/cases.py`, `backend/app/services/casework.py::acknowledge`.

Tests: `backend/tests/test_contract_decisions.py::TestAlertAcknowledgement`.

---

## PC-02 — `alert.safety` field name — **APPROVED**

**Problem.** Every event on the socket is `{type: <event name>, ...payload}`, and the v1 `alert.safety` payload had its own `type` field. The two collided.

**Frozen.**
- The alert kind is `alert_type` everywhere: the `alert.safety` event, the `escalation.packet` alerts, the packet and queue read models, and every mirror.
- The envelope's `type` is always the event name; the server builds frames as `{**payload, "type": event}`, so payload content can never overwrite it.

Tests:
- `test_role_fanout.py::test_a_payload_can_never_rename_the_event`
- `test_contract_decisions.py::test_alert_frames_keep_the_event_name_in_type`

---

## PC-03 — overrides and timeline — **REJECTED (audit-only shortcut); dedicated tables**

The audit-only storage used in the slice is rejected. The implementation:

- `overrides(id, case_id, officer_id, from_band, to_band, reason NOT NULL, created_at)` is the authoritative store of band overrides.
- `timeline_events(id, case_id, stage, label, dedupe_key, created_at)`, unique on `(case_id, dedupe_key)`, is the authoritative victim-safe timeline.
- Each write also records an `audit_log` entry (`band.override`, `timeline.stage_added`) for accountability. The audit log is not the timeline.

**Migration** `7fbad9360da7` preserves local data:
- It copies earlier `band.override` and `timeline` audit events into the new tables, mapping retired stages: `support_arranged` becomes `action_taken`; `officer_speaking` and `recorded` stay in the audit log only.
- It modifies no audit row.
- It is reversible.

**Table count:** 13 → **15**.

Tests:
- `test_contract_decisions.py::TestDedicatedTables`
- `test_contract_mirror.py::TestTableList`

---

## PC-04 — Assignment and takeover updates on the socket — **DEFERRED**

Deferred, not rejected. The console keeps polling `GET /queue` and refetches `GET /cases/{id}` after any socket event. A future proposal remains:

```
case.assignment  {case_id, status, assigned_officer_id}
```

---

## PC-05 — WebSocket authentication out of the URL — **APPROVED IN PRINCIPLE, phased**

**Frozen target protocol** (CONTRACTS §1):
1. The socket connects without a JWT query parameter.
2. The client sends `{"type":"auth","token":...}` immediately after connecting.
3. No session or assessment data is sent before authentication succeeds.
4. Authentication has a short timeout (5 s).
5. An invalid or expired token closes the connection.
6. Tokens are never logged.

**Transitional.** `?token=` stays temporarily supported for the text-first web slice. `backend/app/core/log_redaction.py` redacts it in every log line, as verified by the live smoke test. `POST /sessions` already returns `ws_url` without a token (PC-09).

**Implementation owners:** Backend and Executive Web. The mobile socket moves at the same time.

---

## PC-06 — Supervisor reassignment — **DEFERRED**

The supervisor view stays read-only. Supervisors get 403 on every console write (claim, ack, decisions, override, takeover, messages). A future `POST /cases/{id}/reassign {officer_id, reason}` would need its own proposal.

---

## PC-07 — Officer messaging after takeover — **APPROVED WITH STRICT LIMITS**

**Frozen.**

```
POST /cases/{case_id}/messages   {text, lang?}
  auth   executive only; the officer must have claimed the case
  state  case.status = taken_over, sessions.human_joined_at set (the AI is muted)
  201    {turn_id, case_id, origin:"human_officer", ts}
  409    before takeover, on another officer's case, or after the session ended
  403    supervisor or victim token
  400    blank, or more than 2000 characters
victim event  officer.message {turn_id, text, lang, ts, origin:"human_officer"}
```

- The message is stored as a turn with `speaker:"officer"` and audited as `officer.message` with the turn id and length, never the text.
- It carries no assessment field and is never AI-generated or AI-rephrased. The only publisher is `casework.officer_message`, which a test enforces.
- The event was added to the backend `VICTIM_ALLOWED` and the mobile allowlist in the same change as its safety tests: `test_contract_decisions.py::TestOfficerMessage`, `test_role_fanout.py`, `mobile/tests/contract-gap.test.js`.

The proposal originally used a socket UP event. The decision uses REST instead, because every console write already goes through REST, which has Bearer authentication and role checks. Officer text is written by a person, so it does not pass through the AI output validator. `docs/dialogue/STATES.md` (SH) records this.

---

## PC-08 — Text-channel SVI renormalisation — **APPROVED CONDITIONALLY**

```
weight_denominator = Σ weights of available dimensions        (0.88 when only D4 is absent)
normalized_svi     = Σ(weight × score over available) / weight_denominator
```

- Weights are rescaled **only** for a dimension that is structurally unavailable on the channel: D4 on `mobile_chat` or `portal_chat`.
- Each assessment stores `scoring_version` (`svi-2026.09-pc08`), the available and structurally unavailable dimensions, the denominator and the normalisation factor.
- Hard overrides apply independently. Band thresholds apply to the normalised value.
- The console shows that D4 was unavailable. D4 is never reported as measured and never set to zero.
- There is no rescaling for poor audio, runtime failure or low confidence. On an audio channel, a D4 that was not measured makes the assessment abstain (`acoustic_not_measured`).
- Fixed alongside: `band_for` left gaps between bands (54.5 fell through to Low). The bands are now lower bounds, 0/30/55/75.

Tests: `ml/tests/test_svi_normalization.py` covers:
- boundaries
- sensitivity
- determinism
- explanation
- D4 is never zero
- no rescaling when D4 is missing for other reasons

---

## PC-09 — `POST /sessions` response — **APPROVED AND FROZEN**

`{session_id, case_id, reference_no, session_token, ws_url, lang, consent, ai_disclosure, human_request_available}`. There are no other fields (`extra="forbid"`).

- `session_token` is the victim credential for that one session. It never authorises a console route or another session.
- `ws_url` is a path with no token.
- The executive token comes only from `/auth/login`.
- Removed from the earlier response: `token` (renamed `session_token`) and `state`.

---

## PC-10 — Enumerations and error shape — **FROZEN**

CONTRACTS §9 freezes these values using HANDOVER vocabulary:
- timeline stages
- session channel
- recommendation pathways
- case status
- consent status
- session states
- bands
- the Needs Human Assessment representation
- decisions
- alert type and severity
- roles
- turn speakers
- the error response shape

The documented differences are `emergency` as a pathway, `closed` covering "closed/continuing", and case status, which HANDOVER does not enumerate.

- Backend source: `backend/app/core/enums.py`. The Pydantic `Literal`s are built from it, and the duplicate backend timeline lists are gone.
- Mirrors: `frontend/src/types/contracts.ts` and `ml/assessment.py` (`TEXT_CHANNELS`).
- The mirror test checks all of them: `test_contract_mirror.py::TestEnumMirror`.
