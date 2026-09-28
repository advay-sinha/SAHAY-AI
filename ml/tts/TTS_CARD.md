# Component card — voice output (fixed scripts and TTS)

| Field | Value |
|---|---|
| Components | `ml/tts/presynth.py` (fixed-script recordings registry), `ml/tts/synthesize.py` (built-in Windows voices), backend `GET /sessions/{id}/turns/{turn_id}/audio` (PC-12) |
| Decision | EXT-103: fixed scripts come from **human recordings**; validated generated turns may use a **built-in offline OS voice**. No TTS model is downloaded. |

## Rules

- **Fixed scripts (S0, S9, SX, SH) are never synthesised.** A recording is served only when all of these hold:
  - the script text is APPROVED;
  - the recording is of the current approved text;
  - a named reviewer who did not make the recording approved it;
  - its hash still matches.

  Otherwise the endpoint returns 404 and the phone shows the text.
- **Other assistant turns** exist only for text that passed the validator or is language-approved fallback. They are synthesised once, then cached. `TTS_PROVIDER` defaults to `none`.
- **No cross-language fallback.** Hindi has no installed Windows voice on the demo laptop, so Hindi turns stay text-only; they are never read out by an English voice.

## Measured

- **Offline English voice** (en-IN Heera): a whole reply sentence in p50 31 ms and p95 38 ms, against a 500 ms first-chunk budget. The whole file counts as the first chunk. Setup: warm worker, 6 fictional sentences on the laptop.
- **Today nothing is actually spoken to a victim:**
  - every fixed script is unapproved;
  - no recording is registered;
  - no intent text has passed language review yet.

## Still needed

- Approved fixed-script texts, human recordings and reviewer approval (human tasks).
- A Hindi voice, or recorded Hindi audio.
- Playback checked on a real phone.
