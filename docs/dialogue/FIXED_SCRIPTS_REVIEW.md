# Fixed scripts — decisions required before anything is written

Status: **S0, S9, SX and SH are unwritten.** This file lists what a human must
decide *before* wording is drafted. It contains no victim-facing text, by
design.

Owner: Team A / A2. S0 and S9 due before Day 3. SX additionally requires a
counsellor or psychology faculty review before Day 8, and that reviewer must be
named in the deck.

Populating a script is a `type:dialogue` change: two reviewers, one of them
running the `dialogue-safety-reviewer` agent, with `docs/dialogue/STATES.md`
updated in the same commit.

## Fail-closed behaviour — unchanged, do not weaken

Until a record is marked `APPROVED` with a named reviewer and a review date:

- `ml/dialogue/scripts/fixed_scripts.py` → `text_for()` returns `None`
- `ml/dialogue/policy.py` → returns `script_available: False`
- `backend/app/services/turn_loop.py` → raises `FixedScriptUnavailable`
- `GET /health` → reports `fixed_scripts_ready: false` and lists what is missing
- `ml/tests/test_pure_modules.py` → fails if a script becomes speakable without
  a named reviewer and a review date

Nothing unreviewed can reach synthesis. Do not add a placeholder string to make
a demo run.

### Provisional local-demo exception (Task 5D-L, EXT-120, PC-12)

The records above stay `NOT_WRITTEN` and every statement in the list above
still holds. Separately, `ml/dialogue/scripts/provisional.py` holds the eight
Task 5C candidate texts, copied byte for byte from the candidate packet after
their hashes were verified. They are **provisional, unreviewed and local-demo
only**; no reviewer, approval or date is recorded for any of them.

`backend/app/services/fixed_scripts.py` may show them only when
`PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO=true`, which settings refuse unless
`APP_ENV` is `development` or `test`. When shown:

- they are text only, `audio:"none"`, never `"prerecorded"` or `"streaming"`;
  there is no audio asset and audio readiness is false;
- a text whose hash no longer matches is suppressed and audited;
- S0 and SH appear only with granted consent; SH only on first entry, never
  over SX or after a verified takeover; SX once on crisis entry, with crisis
  routing, Critical, the alert and the takeover request unchanged; S9 once,
  after session end is persisted, never after SX, SH or takeover, and only when
  a victim turn was recorded;
- S9 receives the session's own persisted reference through the single
  `{reference_no}` slot after ownership, format (`^SAH-[0-9A-F]{6}$`) and
  equality checks; any failure suppresses S9 and records a reason code;
- the turn is persisted with `review_status="provisional_unreviewed"`, and the
  audit records the script hash, never victim text.

This exception does not satisfy the approval gate below.

## Candidate review packet

Task 5C candidate wording is recorded in
[`FIXED_SCRIPTS_CANDIDATE_REVIEW.md`](FIXED_SCRIPTS_CANDIDATE_REVIEW.md).
Every candidate remains `PENDING`; the packet is not an approval record and
does not make any script speakable. This canonical record remains the approval
gate.

---

## S0 OPENING — decisions required

Required content is already fixed by `STATES.md`: identifies the assistant as an
AI, states that a human officer reviews everything, states the right to a human
at any time, invites the person to speak in their own words. No question.

| # | Decision | Who decides |
|---|---|---|
| S0-1 | How the assistant names itself. A product name, "an automated system", or neither. This sets whether the app is perceived as government-operated. | Project owner + legal |
| S0-2 | Whether the opening states that the conversation is recorded, or whether that stays only on the consent screen. | Legal + Team A |
| S0-3 | Whether NHAA 14566 is named in the opening. | Project owner |
| S0-4 | Sentence count. `STATES.md` writing rules say one sentence per utterance; S0 carries four required facts. Confirm S0 is an explicit exception and how many sentences are permitted. | Two dialogue reviewers |
| S0-5 | Hindi register: formal (आप) throughout, confirmed. Whether any Hinglish is permitted in the Hindi script. | Native-speaker reviewer |
| S0-6 | Whether the invitation to speak is open ("tell me what happened") or bounded. An open invitation is what S1 expects. | Team A |

**Bilingual wording needed:** one Hindi and one English script, each covering
S0-1 through S0-6, reviewed by a native Hindi speaker for register and for
absence of the prohibitions in `STATES.md`.

---

## S9 CLOSING — decisions required

Required content: confirms the account is recorded, gives the reference number,
states what happens next. **No promise of outcome.**

| # | Decision | Who decides |
|---|---|---|
| S9-1 | Reference-number format, and whether it is spoken digit by digit, displayed only, or both. Spoken long numbers are a known failure point on a poor line. | Project owner + Team B |
| S9-2 | What "what happens next" may factually claim. This is the highest-risk sentence in the intake: it must describe process without promising a timeline, an arrest, an outcome or compensation. | Legal + project owner |
| S9-3 | Whether a callback expectation is set at all. If the demo cannot support callbacks, the script must not imply one. | Project owner |
| S9-4 | What the closing says when the assessment abstained (`needs_human`). Confirm it is identical to the normal closing — the victim must not be able to infer an assessment from wording. | Two dialogue reviewers |
| S9-5 | Whether the closing repeats the right to a human. | Team A |

**Bilingual wording needed:** one Hindi and one English script. S9-2 wording
should be signed off verbatim rather than paraphrased in review.

---

## SX CRISIS INTERRUPT — decisions required

Required content: acknowledges; states plainly that a person will speak with
them now; asks them to stay. **Nothing else — no advice, no assessment, no
question.**

| # | Decision | Who decides |
|---|---|---|
| SX-1 | Named counsellor or psychology faculty reviewer, and the date of review. Blocks the Day 8 gate. | Project owner |
| SX-2 | The acknowledgement itself. It must not minimise, and every minimising phrase in `ml/guardrails/lexicons/prohibitions.py` is already banned in both languages. Confirm the chosen phrasing against that list. | Counsellor + two dialogue reviewers |
| SX-3 | What is promised about the human. "A person will speak with you now" is only sayable if the demo can actually deliver it. Decide the wording for the case where no executive is available. | Project owner + Team B |
| SX-4 | Whether a helpline number is spoken. Referring a person elsewhere mid-crisis is a clinical decision, not a product one, and `banned_patterns.py` currently blocks phone numbers in generated output. | Counsellor + legal |
| SX-5 | Whether SX says anything at all about what was detected. The recommendation is that it does not; confirm explicitly. | Counsellor |
| SX-6 | What the victim hears while waiting, since SX does not return to intake and the session holds. Silence, a repeat, or a held-line message. | Team A + Team C |
| SX-7 | Whether SX differs when the crisis language was attributed to another person (`he told me to kill myself`). The pre-check currently fires on both. | Counsellor |

**Bilingual wording needed:** one Hindi and one English script, each reviewed by
the named counsellor *and* by a native Hindi speaker. The Hindi is not a
translation exercise: it must be reviewed as crisis language in its own right.

---

## SH HUMAN HANDOFF — decisions required

Required content: confirms the transfer and asks the person to stay.

| # | Decision | Who decides |
|---|---|---|
| SH-1 | Wording for a handoff the victim requested, versus one the system escalated. Confirm whether these are one script or two. | Team A |
| SH-2 | What is said when consent was declined and the session routes to a person anyway. | Legal + Team A |
| SH-3 | The takeover notification: the victim must hear, in their language, that a person has joined. Confirm whether this is part of SH or a separate string. | Team A + Team C |
| SH-4 | Expected wait wording, if any. Do not state a duration the demo cannot meet. | Project owner |

---

## After each script is approved

1. Fill the `ScriptRecord` in `ml/dialogue/scripts/fixed_scripts.py`: `text`,
   `status="APPROVED"`, `reviewer`, `review_date`.
2. Pre-synthesise to WAV, store under `DATA_ROOT/audio/fixed/`, and record the
   asset name in `ml/tts/presynth.py`. **Audio is never committed.**
3. Update `docs/dialogue/STATES.md` in the same commit.
4. Confirm `GET /health` reports `fixed_scripts_ready: true`.
5. TTS voice selection is EXT-103 and still `PROPOSED`. Pre-synthesis needs its
   own approval before any voice is downloaded.
