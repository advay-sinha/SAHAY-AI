# Limitations — SAHAY-AI ML (national MVP)

This page states what the evidence does **not** support. Every number referred to is in `NUMBERS.md` or the evaluation table, with its evidence class.

## 1. Evidence

- **No independent evaluation exists yet.**
  - The locked set has 0 samples; its crisis and danger fixtures need two human reviewers each.
  - The blind corpus has not been written; it must be written by people who did not build the system.
  - Every safety number today comes from **exposed** fixtures, published during development. It shows regression behaviour, not generalisation.
- **The fictional training corpus had a shortcut.** In `7b-v1`, every multi-turn record carried a risk label. Measured on `7b-v2` (R10):
  - The logistic baseline relied on it: `[SEP]` was its top feature.
  - MuRIL did not: only 2.4% false alarms on harmless multi-turn records.
  - The v1 models were weak on mixed multi-turn records (0.34–0.42 macro F1). v2 training fixes that (0.69–0.79), at the cost of more false alarms.
  - Per-label rates remain only partly balanced in `v2`.
- **Borrowed-label results are weak-supervision evidence.** The labels are:
  - which subreddit a post came from;
  - a hate-speech label;
  - crowd-annotated stress.

  None of these is a SAHAY judgement.
- **Speech-emotion results are on acted English speech only** (RAVDESS, CREMA-D). Nothing is measured on Hindi, Hinglish, telephone audio or real distress.
- **Latency was measured on the laptop with synthetic speech.** The phone's end-of-speech wait (700 ms) is configured, not measured. Wi-Fi upload, playback start on the phone and Hindi are not measured.
- **Small numbers.** Per-language fixture counts are 12–28 records. Rates carry wide intervals and are shown with their denominators.

## 2. Languages

| Language | Rules and crisis pre-check | Speech-to-text | Voice output | Speech emotion |
|---|---|---|---|---|
| English | yes | yes (Whisper Small) | yes (built-in voice) | acted-speech results only |
| Hindi, Devanagari | yes | supported; WER not measured | **no voice installed**: text only | not measured |
| Hinglish, romanised | yes | only as the Hindi or English path | English voice only if the text is English | not measured |

No other language is claimed.

## 3. Models

- **The deterministic rules are authoritative.** They are precise on explicit phrasing and miss indirect, figurative and regional wording (P-DET-4).
- **Shadow MuRIL (Stage W)**
  - It is well below the rules on SAHAY fixtures: micro F1 0.60 against 0.93 on dev, and 0.58 against 0.88 on candidates.
  - It fires on harmless absence wording ("I won't be here tomorrow").
  - It never routes, scores or speaks; its status is `rejected_for_product_integration`.
- **Text affect and speech emotion** are shadow-only. The speech-emotion slot in D4 is off until its gate passes on team recordings.
- **D4 (voice distress)** is an unvalidated rule. Its weights and scale are design choices.
- **SVI weights** are provisional design choices awaiting expert calibration. On text, Critical is reachable only through the crisis or immediate-danger override (P-SVI-1).

## 4. Pending human reviews

Several lexicons and rules are **drafts until two people review them**:
- the crisis lexicon (`crisis-v1.2-unreviewed`);
- the detector lexicons (`detectors-v1.2-draft`);
- the output rules (`output-rules-1.1-unreviewed`);
- the fixed scripts (none approved).

Until the fixed scripts are approved, the system fails closed: nothing unreviewed is spoken.

## 5. Data and privacy

- Only fictional text is used in fixtures, tests and the demo. No real victim data exists in the MVP (invariant 8).
- Public datasets are used for training and validation under EXT-129. Their licences are recorded as pending, and weights derived from them stay private and are never shipped.
- The runtime database is Supabase PostgreSQL, the backend lead's change of 2026-09-12. Its external-decision record is still to be added.

## 6. Never claimed

Clinical validity, diagnosis, production readiness, accuracy on real victims, official metrics while the locked set is empty, and support for untested languages.
