# Rule card — D4 acute distress from voice (`d4-prosody-1.0`)

| Field | Value |
|---|---|
| Identity | Plan step M12h; decisions D-4 (EXT-121) and D-8; code `ml/acoustics/d4.py` (standard library only) |
| What it measures | How far a caller's later voice turns move **upwards** from their own first two usable turns in median pitch, pitch variability, loudness and pause ratio, in units of that caller's own spread |
| Formula | Per turn: 25 × (0.35·f0 + 0.20·pitch variability + 0.20·loudness + 0.25·pause ratio), with each deviation's positive part only, capped at 100. D4 is the highest turn score. |
| Inputs | Prosody from the loopback speech-to-text process: YIN pitch with clip-relative voicing, RMS level, VAD pauses. Stored on the turn in `turns.asr_quality`. |
| Confidence | 0.40 + 0.05 per compared turn, capped at **0.60** |
| Weight in the SVI | 0.12 (provisional, like every weight) |

## Safeguards (enforced and tested)

- **At least 3 usable voice turns.** With fewer, D4 is unmeasured and the assessment abstains (PC-08).
- **Poor-audio or low-ASR-confidence turns are excluded.** Either condition also makes the whole assessment abstain.
- **Only upward deviation counts.** A flatter or quieter voice is never read as calm or as low mood.
- **Speech-emotion input is OFF** (`SER_ENABLED = False`). Once enabled after the R7 gate, it can never exceed 30% of D4.
- **Hard overrides are unaffected.** Crisis language or confirmed danger forces Critical whatever D4 says; a test covers a calm voice with crisis words.
- **SAFE-SIGNAL:** if D4 and text severity (the highest of D1, D2, D3, D5) differ by more than 40 points, the console shows a neutral "please verify" prompt in the uncertainty block. It is never an alert and never changes the band.
- **Never victim-facing.**

## Evidence

**Unvalidated.** The rule encodes the documented association between acute arousal and raised, more variable, louder or more hesitant speech relative to the same speaker. Its weights and the 25-points-per-unit scale are design choices, not fitted values. What exists:

- unit tests on synthetic features, covering the rule, the thresholds, the cap and the abstention paths;
- on acted corpora, speaker normalisation improved a prosody classifier by 0.05–0.14 UAR, which supports the in-session design, not this particular formula;
- nothing measured on real or Indian telephone speech.

Validating it needs the team recordings (H5) and, ultimately, expert review of the D4 weight (H11).

## Limitations

- A caller who is already distressed in their first two turns has a distressed baseline, so D4 underestimates them. Text dimensions and the crisis check are unaffected.
- Background changes such as moving to a noisier room can raise loudness and pause measures. Poor-audio exclusion catches only severe cases.
- Pitch tracking was tuned on acted studio speech.
