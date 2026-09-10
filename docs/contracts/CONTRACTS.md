# Frozen contracts — v1

> **Local MVP infrastructure profile:** SQLite through SQLAlchemy replaces PostgreSQL for the current build; a local background runner replaces Redis/RQ; local retrieval replaces pgvector. Provider interfaces must preserve a later migration path. Safety, event, REST and pure-module contracts below are unchanged.

Agreed Day 1. Changed only via an issue labelled `type:contract` with **all three team leads** approving, and only through `/contract-change`. Never inside a feature PR.

Every team builds against this file, not against another team's current code.

---

## 1. Transport

```
WSS /ws/session/{session_id}?token=<jwt>

UP    binary   16 kHz mono PCM16 · 500 ms frames · 8-byte header: uint32 seq | uint32 ms
      text     {"type":"chat.message","text":...,"lang":...}
               {"type":"request_human"}
DOWN  binary   assistant TTS chunks, prefixed with turn_id header
      text     events below

FALLBACK       POST /sessions/{id}/audio     whole-utterance upload (always available)
RECONNECT      client resumes from last acknowledged seq; server de-duplicates
```

---

## 2. Events — victim client MAY receive

```
assistant.turn    {turn_id, text, lang, intent, audio:"streaming"|"prerecorded"}
transcript.line   {turn_id, speaker:"victim"|"assistant", text, lang, ts}
session.status    {state, consent, lang, human_joined:bool}
timeline.update   {stage, label, ts}
```

## 3. Events — EXECUTIVE CONSOLE ONLY

**Enforced server-side by role on the socket** (`backend/app/ws/fanout.py`). A client-side filter is not acceptable. `backend/tests/test_role_fanout.py` asserts a victim token cannot receive these.

```
dimension.update   {dims:{D1..D9:{score, conf, evidence_turn_ids[]}},
                    svi, band, needs_human, overrides_applied[]}
alert.safety       {type:"crisis"|"threat"|"medical"|"coercion", severity,
                    evidence_turn_ids[], requires_ack:true}
case.structured    {incident, timeline[], persons[], threats[], safety_now,
                    medical_need, legal_status, isolation, requested_support}
action.recommended {action_id, action_type, rationale, policy_citations[], confidence}
safesignal.flag    {direction, delta, suggested_question}
escalation.packet  {case_id, band, alerts[], summary, ready:true}
```

---

## 4. REST

```
POST /auth/login
POST /sessions                 {channel, consent, lang}
POST /sessions/{id}/audio      whole-utterance fallback
POST /sessions/{id}/end
GET  /queue
GET  /cases/{id}               full escalation packet
POST /cases/{id}/claim
POST /cases/{id}/decisions     {action_id, decision:"confirm"|"modify"|"reject",
                                rationale, officer_id}
POST /cases/{id}/override      {band, reason}          # reason REQUIRED
POST /cases/{id}/takeover
GET  /cases/{id}/timeline      victim-safe view — must contain no assessment field
GET  /cases/{id}/audit
```

---

## 5. Module interfaces — pure functions, no I/O

```python
dialogue.next(state, slots, utterance, safety_flags)
    -> {next_state, intent, licensed_question, fallback_text}

guardrails.validate(text, intent, lang)
    -> {ok: bool, reason: str, safe_text: str}

svi.compute(dimension_scores, confidences, quality)
    -> {svi, band, needs_human, breakdown, overrides_applied}
```

---

## 6. Database tables

`users · sessions · consents · turns · cases · assessments · alerts · recommendations · decisions_ai · decisions_human · audit_log · policy_chunks (pgvector) · latency_metrics`

`decisions_ai` and `decisions_human` are **separate tables**. The record must never read as though a machine decided.

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
