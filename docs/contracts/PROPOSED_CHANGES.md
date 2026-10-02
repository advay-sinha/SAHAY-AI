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

---

## PC-11 — `POST /sessions/{id}/audio` request and response — **APPROVED AND FROZEN (2026-09-27)**

Plan step M11, decision EXT-120. Applied to `CONTRACTS.md` §1 and §4 after lead confirmation. Addition while applying: the audio measurements are stored in a new nullable column, `turns.asr_quality` (JSON; the table list in §6 is unchanged).

```
CONTRACT CHANGE PROPOSAL
Contract:     POST /sessions/{id}/audio   (CONTRACTS §1 FALLBACK line, §4 REST)
Current:      "whole-utterance fallback (501 in the text-first slice)". No request or response shape.
Proposed:
  POST /sessions/{id}/audio?lang=hi|en        victim session token (same rule as /sessions/{id}/end)
    body        raw audio bytes; Content-Type audio/wav (16-bit PCM, mono, 8–48 kHz)
                | audio/mp4 | audio/aac (M4A/AAC, what expo-audio records on Android)
    limits      ≤ 60 s of audio, ≤ 5 MB
    lang        optional; defaults to the session language; only hi and en
    200 →       {turn_id: string | null, status: "accepted" | "no_speech" | "audio_unreadable"}
    errors      413 too large · 415 unsupported Content-Type · 409 not an audio-channel session
                (mobile_voice | upload), consent declined, or session not in intake ·
                503 ASR unavailable (client offers Chat). Error body follows CONTRACTS §9.
    semantics   "accepted": the transcript enters the SAME path as chat.message — crisis
                pre-check first, then the dialogue policy — and the victim receives the
                unchanged transcript.line and assistant.turn events. The response never
                contains a transcript confidence, audio quality, emotion, score or band.
    console     ASR confidence is stored on the turn (existing column turns.asr_confidence)
                and reported in the existing assessment `uncertainty` block together with
                speech duration and audio quality. Low confidence or poor audio makes the
                assessment abstain (needs_human, invariant 6). No new event, field or enum.
Reason:       Voice intake (VF-11, M11). Without it, no spoken turn can reach the dialogue.
Breaks:       Nothing; additive. Backend: the 501 stub in backend/app/api/sessions.py is
              replaced. Frontend: none. Mobile: none yet (capture is a stub; it becomes a
              consumer later). ML: none.
Migration:    Additive. No data migration (turns.asr_confidence already exists).
Alternative:  Voice stays an ML-owned local demonstration; the product stays text-only.
```

Internal, not part of the contract: the backend reaches speech recognition through an ASR adapter (`ASR_PROVIDER=mock` by default, or `local_service`). `local_service` calls a separate local speech-to-text process, owned by the ML team, that binds to 127.0.0.1 only and runs voice-activity detection before speech recognition. This is within EXT-120: local only, no public listener.

| Lead (D-11) | Confirmation |
|---|---|
| AI/ML and Safety | Project owner, 2026-09-27 |
| Backend | Confirmed 2026-09-27, relayed by the project owner |
| Executive Web | Confirmed 2026-09-27, relayed by the project owner |
| Mobile/Victim Experience | Confirmed 2026-09-27, relayed by the project owner |

## PC-12 — `GET /sessions/{id}/turns/{turn_id}/audio` — **APPROVED AND FROZEN (2026-09-29)**

Plan step M13, decision EXT-103. Applied to `CONTRACTS.md` §4.

```
CONTRACT CHANGE PROPOSAL
Contract:     GET /sessions/{id}/turns/{turn_id}/audio   (CONTRACTS §4 REST)
Current:      none. assistant.turn carries audio:"prerecorded"|"streaming", but no frozen
              interface says where the client obtains that audio.
Proposed:
  GET /sessions/{id}/turns/{turn_id}/audio    victim session token for that session only
    200 → audio/wav (16 kHz mono), Cache-Control: no-store
    404 → no approved audio: not an assistant turn of this session, a fixed script without an
          approved human recording, or no voice for the language. The client keeps the text.
    403 → any other token
  semantics   fixed scripts (S0/S9/SX/SH) come only from approved human recordings (hash-checked,
              reviewer is not the recorder, recording of the current approved text), never TTS.
              Other assistant turns are validated or language-approved text; they may be spoken
              once by the configured offline voice and cached.
Reason:       Voice output (M13). Without it the approved audio sources of EXT-103 cannot reach
              the phone.
Breaks:       Nothing; additive. Backend: new route, TTS adapter (TTS_PROVIDER, default none),
              FIXED_AUDIO_ROOT. Mobile: optional consumer (request builder and player).
              Frontend: none. ML: ml.tts.presynth registry and ml.tts.synthesize voice wrapper.
Migration:    None. Synthesis timing uses the existing latency_metrics table.
Alternative:  The phone shows text only; fixed-script audio would have to be bundled in the app.
```

| Lead (D-11) | Confirmation |
|---|---|
| AI/ML and Safety | Project owner, 2026-09-29 |
| Backend | Confirmed 2026-09-29, relayed by the project owner |
| Executive Web | Confirmed 2026-09-29, relayed by the project owner |
| Mobile/Victim Experience | Confirmed 2026-09-29, relayed by the project owner |


---

## PC-13 — Hosted tester guard on `POST /sessions` — **APPROVED (2026-10-01); A applied, B not built**

Decision EXT-130 (hosted tester deployment). Opt-in: with neither setting present, behaviour is
exactly the frozen PC-09 contract, so local and demo builds are unchanged.

```
CONTRACT CHANGE PROPOSAL
Contract:     POST /sessions   (CONTRACTS §4 REST, PC-09)
Current:      {channel, consent, lang} → 201 CreateSessionResponse; anyone who can reach
              the backend can create sessions without limit.
Proposed:
  A. Rate limit (backend setting SESSION_RATE_LIMIT_PER_HOUR, default 0 = off)
     429 → {"detail": "too many sessions; try again later"} once a client IP exceeds the
           limit in a rolling hour. The IP comes from the proxy's forwarded header.
  B. Tester access code (backend setting TESTER_ACCESS_CODE, default empty = off)
     Request header  X-Tester-Code: <code>
     403 → {"detail": "access code required"} when the setting is on and the header is
           missing or wrong (constant-time compare; the code is never logged or echoed).
     Client: the tester types the code once on the language screen; it is held in memory
             only, like the session token. It cannot be baked into the web build:
             EXPO_PUBLIC_* values are readable by anyone who loads /victim.
  Both use the frozen PC-10 error shape. The response body on success is unchanged.
Reason:       The hosted backend is on a public URL. Without a guard anyone who finds it can
              create unlimited sessions and fill the executive queue.
Breaks:       Nothing when off; additive. Backend: api/sessions.py (+ settings, tests).
              Mobile: restClient createSession (header), language screen input and two
              strings for B only. Frontend: none (the console never creates sessions).
              ML: none.
Migration:    None. No stored data changes.
Alternative:  Keep the URLs unshared and invite-only (current EXT-130 scope) and watch the
              queue during test windows; tear down if it is abused.
Recommendation: A now (backend only, no UI). B only if the URL leaks.
```

| Lead (D-11) | Confirmation |
|---|---|
| AI/ML and Safety | Confirmed 2026-10-01, relayed by the project lead |
| Backend | Confirmed 2026-10-01, relayed by the project lead |
| Executive Web | Confirmed 2026-10-01, relayed by the project lead |
| Mobile/Victim Experience | Confirmed 2026-10-01, relayed by the project lead |

Applied to `CONTRACTS.md` §4: option A (rate limit). Option B (access code) stays unbuilt, per the recommendation, until the hosted URL leaks.

---

## PC-14 — Advisory model signals for officers — **APPROVED (2026-10-02)**

Decision EXT-133.

```
CONTRACT CHANGE PROPOSAL
Contract:     assessments table; GET /cases/{id} packet; executive WebSocket events
Current:      no model output reaches the backend or the console.
Proposed:
  table       assessments.model_signals JSON, nullable (null when no signal service ran)
  packet      "model_signals": the latest cycle's value, or null
  event       "model.signal" (executive and supervisor only; never victim)
  shape       {status: "loaded"|"unavailable"|"failed", model: "experimental_shadow_classifier",
               checkpoint_status: <str>, advisory: true, uncalibrated: true,
               labels: {<label>: {probability: float, fired: bool}} for
                 crisis_self_harm, communication_safety_coercion, legal_urgency only,
               flag: bool  -- true when the model fired crisis_self_harm and the rules
                            did not; the console asks the officer to review}
Reason:       Rules plus models: a model may add caution for a human to check, never remove it.
Breaks:       Nothing; additive. Backend: migration, worker, packet, events allowlist.
              Frontend: types, a read-only panel. Mobile: none (the victim never receives it).
Migration:    One nullable column; old rows stay null.
Alternative:  Signals shown only in the local ML demonstration (current state).
```

| Lead (D-11) | Confirmation |
|---|---|
| AI/ML and Safety | Confirmed 2026-10-02, relayed by the project lead |
| Backend | Confirmed 2026-10-02, relayed by the project lead |
| Executive Web | Confirmed 2026-10-02, relayed by the project lead |
| Mobile/Victim Experience | Confirmed 2026-10-02, relayed by the project lead |

