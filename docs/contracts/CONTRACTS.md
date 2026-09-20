# Frozen contracts — v2

> **Local MVP infrastructure profile:** SQLite through SQLAlchemy replaces PostgreSQL for the current build; a local background runner replaces Redis/RQ; local retrieval replaces pgvector. Provider interfaces must preserve a later migration path.

Agreed Day 1 (v1). Changed only via an issue labelled `type:contract` with **all team leads** approving (D-11: AI/ML and Safety, Backend, Executive Web, Mobile/Victim Experience), and only through `/contract-change`. Never inside a feature PR.

**v2, 2026-09-11.** Applies the lead decisions on PC-01 to PC-10 (`docs/contracts/PROPOSED_CHANGES.md`, decisions recorded there). Summary: PC-01 alert acknowledgement frozen · PC-02 `alert_type` frozen · PC-03 dedicated `overrides` and `timeline_events` tables · PC-04 queue push **deferred** · PC-05 socket auth target protocol frozen, phased · PC-06 supervisor actions **deferred**, supervisor view read-only · PC-07 officer messaging frozen with strict limits · PC-08 renormalisation over structurally unavailable dimensions · PC-09 `POST /sessions` response frozen · PC-10 enumerations and error shape frozen.

Every team builds against this file, not against another team's current code.

---

## 1. Transport

```
WSS /ws/session/{session_id}

UP    binary   16 kHz mono PCM16 · 500 ms frames · 8-byte header: uint32 seq | uint32 ms
      text     {"type":"auth","token":<session_token or executive token>}   (PC-05, first frame)
               {"type":"chat.message","text":...,"lang":...}
               {"type":"request_human"}
DOWN  binary   assistant TTS chunks, prefixed with turn_id header
      text     events below

FALLBACK       POST /sessions/{id}/audio     whole-utterance upload (always available)
RECONNECT      client resumes from last acknowledged seq; server de-duplicates
```

**Socket authentication — PC-05, approved in principle, phased.**

*Target protocol (frozen):*
1. The client connects to `/ws/session/{session_id}` with **no token in the URL**.
2. Its first frame is `{"type":"auth","token":...}`, sent immediately after the connection opens.
3. The server sends **no session or assessment data** before authentication succeeds.
4. Authentication has a short timeout (5 s). Timing out, or an invalid or expired token, closes the connection (close code 4401 or 4403). The server gives no detail about why.
5. Tokens are never logged by client or server.

*Transitional (temporarily supported for the text-first web slice only):* `WSS /ws/session/{session_id}?token=<jwt>`. The server already redacts `token=` values and JWT shapes from its logs (`backend/app/core/log_redaction.py`). Clients build this URL themselves from `ws_url` and the token. They must never persist, display or log it.

*Implementation owners:* Backend (server handshake) and Executive Web (console socket). The mobile app moves at the same time. The query-token form is removed once both sides ship the target protocol and the slice's smoke test passes on it.

---

## 2. Events — victim client MAY receive

```
assistant.turn    {turn_id, text, lang, intent, audio:"streaming"|"prerecorded"}
transcript.line   {turn_id, speaker:"victim"|"assistant", text, lang, ts}
session.status    {state, consent, lang, human_joined:bool}
timeline.update   {stage, label, ts}
officer.message   {turn_id, text, lang, ts, origin:"human_officer"}
```

**The server enforces this allowlist** (`backend/app/ws/events.py` `VICTIM_ALLOWED`). The mobile mirror is `mobile/src/types/events.ts` `ALLOWED_EVENT_TYPES`, and `backend/tests/test_contract_mirror.py` asserts the two lists and this section agree.

**`officer.message` (PC-07).** This event exists only after a verified takeover:
- The sender is an authenticated executive who has claimed the case.
- The case status is `taken_over`, `sessions.human_joined_at` is set and the assistant is muted.
- The message is text typed by that officer, stored as a turn with `speaker:"officer"` and audited. The audit entry records the turn id and length, never the text.
- It carries **no assessment field**.
- It is never AI-generated or AI-rephrased.

## 3. Events — EXECUTIVE CONSOLE ONLY

**Enforced server-side by role on the socket** (`backend/app/ws/fanout.py`). A client-side filter is not acceptable. `backend/tests/test_role_fanout.py` asserts a victim token cannot receive these.

```
dimension.update   {dims:{D1..D9:{score, conf, evidence_turn_ids[]}},
                    svi, band, needs_human, overrides_applied[]}
alert.safety       {alert_type:"crisis"|"threat"|"medical"|"coercion",
                    severity:"high"|"critical", evidence_turn_ids[], requires_ack:true}
case.structured    {incident, timeline[], persons[], threats[], safety_now,
                    medical_need, legal_status, isolation, requested_support}
action.recommended {action_id, action_type, rationale, policy_citations[], confidence}
safesignal.flag    {direction, delta, suggested_question}
escalation.packet  {case_id, band, alerts[{alert_type, severity, evidence_turn_ids[], requires_ack}],
                    summary, ready:true}
```

**Envelope rule (PC-02).** Every text frame is `{"type": <event name>, ...payload}`. The envelope's `type` is always the event name, and payload content can never overwrite it. The server builds frames as `{**payload, "type": event}`. An alert's kind is therefore `alert_type`, never `type`.

In `dimension.update`, a dimension that is unavailable (for example D4 on a typed channel) has `score: null`. It is never `0`.

---

## 4. REST

```
POST /auth/login                          {username, password} → {token, role, display_name}
POST /sessions                            {channel, consent, lang} → CreateSessionResponse (below)
POST /sessions/{id}/audio                 whole-utterance fallback (501 in the text-first slice)
POST /sessions/{id}/end                   → {case_id, reference_no}
GET  /queue                               → band-ranked case summaries, codes only
GET  /cases/{id}                          full escalation packet
POST /cases/{id}/claim
POST /cases/{id}/alerts/{alert_id}/ack    → {alert_id, case_id, acknowledged_by, acknowledged_at}   (PC-01)
POST /cases/{id}/decisions                {action_id, decision:"confirm"|"modify"|"reject",
                                           rationale, officer_id}
POST /cases/{id}/override                 {band, reason}          # reason REQUIRED (400 if blank)
POST /cases/{id}/takeover
POST /cases/{id}/messages                 {text, lang?} → {turn_id, case_id, origin:"human_officer", ts}  (PC-07)
GET  /cases/{id}/timeline                 victim-safe view — must contain no assessment field
GET  /cases/{id}/audit
```

**Authorisation.**
- Console read routes (`/queue`, `GET /cases/{id}`, `/audit`) accept executive and supervisor tokens.
- Console write routes (claim, ack, decisions, override, takeover, messages) accept **executive tokens only**. The supervisor view is read-only (PC-06 deferred), so a supervisor token gets 403.
- A victim token gets 403 on every console route.
- The timeline accepts a victim token for its own case only.

**`POST /cases/{id}/alerts/{alert_id}/ack` (PC-01, frozen).**
- Requires executive authentication.
- The officer must have access to the case: an officer may not acknowledge an alert on a case another officer has claimed (403).
- Records the acknowledging officer and the time.
- Idempotent: a repeat returns the first acknowledgement unchanged.
- Changes neither the assessment, the band, nor the victim timeline, and publishes nothing to the victim.
- An escalated alert (higher severity) clears its acknowledgement and needs a fresh one.

**`POST /cases/{id}/messages` (PC-07, frozen with strict limits).**
- 201 on success.
- 409 before takeover, when the case is claimed by another officer or unclaimed, or after the session has ended.
- 403 for a supervisor or victim token.
- 400 for blank text or more than 2000 characters.
- See section 2.

**`POST /sessions` response (PC-09, frozen).** Only these fields, and unknown fields are rejected (`extra="forbid"`):

```
{
  session_id,               the session
  case_id,                  the case opened for it
  reference_no,             the victim-facing reference, e.g. SAH-2026-XXXXXXXX
  session_token,            VICTIM credential: role victim, scoped to this session_id only
  ws_url,                   "/ws/session/{session_id}" — path only, NO token
  lang,                     "hi" | "en"
  consent,                  "granted" | "declined" | "pending"
  ai_disclosure,            text the client must display
  human_request_available   bool — "Talk to a person" stays available
}
```

- `session_token` is **not** an executive token. Executive tokens come only from `/auth/login`.
- A session token never authorises a console route or any other session. The server returns 403, and `backend/tests/test_vertical_slice.py` asserts this.
- The response carries no session state and no assessment field.
- To connect, a client uses `ws_url` plus the section 1 protocol. During the transition the client appends `?token=<session_token>` itself.

---

## 5. Module interfaces — pure functions, no I/O

```python
dialogue.next(state, slots, utterance, safety_flags)
    -> {next_state, intent, licensed_question, fallback_text}

guardrails.validate(text, intent, lang)
    -> {ok: bool, reason: str, safe_text: str}

svi.compute(dimension_scores, confidences, quality)
    -> {svi, band, needs_human, breakdown, overrides_applied,
        aggregate_confidence, abstention_reasons, weights_are_provisional,
        scoring_version, available_dimensions, structurally_unavailable,
        weight_denominator, normalization_factor}
```

`quality.structurally_unavailable` (PC-08) lists dimensions with no measurement path on the channel. Only `D4` may be listed, and a listed dimension must not also carry a score.

---

## 6. Database tables

`users · sessions · consents · turns · cases · assessments · alerts · recommendations · decisions_ai · decisions_human · overrides · timeline_events · audit_log · policy_chunks · latency_metrics`

That is 15 tables. PC-03 restored `overrides` and `timeline_events` (HANDOVER.md section 11). `policy_chunks` uses local keyword retrieval, not pgvector.

- `decisions_ai` and `decisions_human` are **separate tables**. The record must never read as though a machine decided.
- `overrides` is the authoritative store of band overrides. `reason` is `NOT NULL` and enforced at the endpoint.
- `timeline_events` is the authoritative victim-safe timeline (`stage`, `label`, `created_at`). It is unique per `(case_id, dedupe_key)`.
- `audit_log` is an append-only **accountability record**. Writes to `overrides` and `timeline_events` also add an audit entry. The audit log is not the authoritative timeline or override store.

---

## 7. SVI specification

| Dim | Meaning | Weight |
|---|---|---|
| D1 | Immediate safety threat | 0.22 |
| D2 | Crisis / self-harm language | 0.18 |
| D3 | Fear, intimidation, threats | 0.13 |
| D4 | Acute distress (acoustic + emotional) | 0.12 |
| D5 | Trauma-associated indicators | 0.08 |
| D6 | Social isolation, boycott, displacement | 0.08 |
| D7 | Medical urgency | 0.08 |
| D8 | Legal urgency | 0.06 |
| D9 | Communication safety | 0.05 |

`SVI = Σ(weight_i × score_i)`, scores 0–100.
**Bands:** 0–29 Low · 30–54 Moderate · 55–74 High · 75–100 Critical.
The score is continuous. A value belongs to the highest band whose lower bound (0, 30, 55, 75) it reaches, so 54.5 is Moderate.

**Renormalisation (PC-08, approved conditionally).** Weights are rescaled **only** when a dimension is *structurally* unavailable for the channel: there is no measurement path at all, as with D4 on `mobile_chat` or `portal_chat`.

```
weight_denominator = Σ weight_i over available dimensions      (0.88 when only D4 is absent)
normalized_svi     = Σ(weight_i × score_i over available) / weight_denominator
aggregate_conf     = Σ(weight_i × conf_i over available)  / weight_denominator
```

- Each assessment stores its `scoring_version`, `available_dimensions`, `structurally_unavailable`, `weight_denominator` and `normalization_factor` (= 1 / denominator), in `assessments.scoring_version` and `assessments.normalization`.
- The console displays that D4 was unavailable. D4 is **never** reported as measured and **never** set to zero.
- Hard overrides apply independently of normalisation. Band thresholds apply to the normalised value.
- **No rescaling** for poor audio, runtime failure, a missing model or low confidence. On an audio channel, a D4 that was not measured keeps its weight in the denominator and the assessment abstains (`acoustic_not_measured`).

**Hard overrides (rules beat weights):**
- Confirmed D1 or D2 above threshold ⇒ band = Critical regardless of the weighted sum
- Aggregate confidence < 0.45, or poor audio quality, or low language confidence ⇒ `needs_human: true`, **no score**
- Consent declined ⇒ scoring suppressed entirely

Weights are labelled in the UI as **provisional, pending expert calibration**.

---

## 8. Latency budget

| Stage | Target |
|---|---|
| VAD endpoint | ~700 ms silence |
| ASR final (utterance) | ≤ 0.6 s |
| Safety pre-check | ≤ 0.05 s |
| Dialogue policy | ≤ 0.01 s |
| LLM phrasing | ≤ 0.8 s |
| Output validator | ≤ 0.02 s |
| TTS first chunk | ≤ 0.5 s (0 s for pre-synthesised turns) |
| **Total: victim stops → assistant starts** | **< 3 s** |

Assessment runs on a **parallel** path and never blocks the reply.

---

## 9. Enumerations and error shape (PC-10, frozen)

The backend source is `backend/app/core/enums.py`. Mirrors are `frontend/src/types/contracts.ts` and `ml/assessment.py` (`TEXT_CHANNELS`). `backend/tests/test_contract_mirror.py` parses the block below and fails if any copy disagrees.

<!-- enums:begin -->
```
session_channel         mobile_voice | mobile_chat | portal_chat | upload
text_channel            mobile_chat | portal_chat
session_state           S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9 | SX | SH
consent_status          granted | declined | pending
case_status             open | claimed | taken_over | closed
band                    Low | Moderate | High | Critical
alert_type              crisis | threat | medical | coercion
alert_severity          high | critical
recommendation_pathway  counselling | legal_aid | medical | police | witness_protection | emergency | welfare | follow_up
decision                confirm | modify | reject
role                    victim | executive | supervisor
timeline_stage          request_received | under_review | officer_assigned | action_taken | follow_up_scheduled | closed
turn_speaker            victim | assistant | officer
```
<!-- enums:end -->

- **Needs Human Assessment** is `svi: null, band: null, needs_human: true`. It is never a zero or a hidden number, and per-dimension scores are withheld as well. The console shows the words "Needs Human Assessment". A hard override is the one exception: it can set `needs_human: true` *with* band `Critical`.
- **Timeline labels** are plain language and process-only. They never name the pathway, the score or the band. For example, `action_taken` reads "An officer has taken action on your request".
- **Documented differences from HANDOVER vocabulary:**
  - `emergency` is a pathway required by the problem statement's emergency support.
  - `closed` covers HANDOVER's "closed/continuing".
  - Case status has no HANDOVER enumeration; these values are the enforced state machine.

**Error response shape.** Every non-2xx response is JSON:

```
4xx domain error      {"detail": "<short fixed message>"}
422 validation error  {"detail": [{"loc": [...], "msg": "<message>"}]}   (never echoes the input)
401                   {"detail": "Not authenticated"}     (same text for every auth failure)
500                   {"detail": "Internal error"}        (never a stack trace, secret or case text)
```
