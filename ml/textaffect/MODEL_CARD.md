# Model card — text affect (MuRIL, shadow)

| Field | Value |
|---|---|
| Identity | Plan step M12e–f, decision D-9a (EXT-123, EXT-125, EXT-129) |
| Task | 5 affect classes for one utterance of text: `affect:neutral · happy · sad · angry · fearful` |
| Selected encoder | **MuRIL (Stage A domain-adapted encoder, run `run-20260912-054730`)**, full fine-tune, mean pooling and a linear head. Selected by the predeclared rule (best mean per-language validation UAR: 0.767, against XLM-R base 0.766 and MuRIL base 0.763). The margin is within noise. |
| Training data | Corpus `textaffect-corpus-v2` (sha256 `4fe8c49e…`), sentence-disjoint: 5,184 distinct EmoInHindi sentences (hi), their romanised Hinglish copies, and single-label GoEmotions (en; neutral capped in train and val) |
| Input | Victim transcript text, at most 128 tokens: Devanagari Hindi, romanised Hinglish or English |
| Output | Probabilities over the 5 affect classes: shadow only |
| Weights | Private, beneath `SAHAY_TRAINING_ROOT/textaffect/runs-v2/`. Derived from licence-pending datasets and never shipped to a victim-facing component. |

## Status

| Field | Value |
|---|---|
| Deployment | **Shadow only (D-9a).** Shown in the local ML demonstration, never in the product. |
| Feeds D4 or the SVI | **No.** Product use is D-9b, which activates only when the EmoInHindi and GoEmotions licences are confirmed and recorded, the model passes the D-8 gate on human-written sentences (H6), and a config flag is switched on. |
| Victim-facing, crisis, routing | Never |

## Measured results (2026-09-26/27; sentence-disjoint test; bootstrap 95% intervals, 1,000 resamples)

| Encoder | Hindi (n = 778) | Hinglish (transliterated, n = 777) | Hindi user turns (n = 495) | English (GoEmotions, n = 2,000) |
|---|---|---|---|---|
| **MuRIL Stage A (selected)** | 0.745 [0.709, 0.779] | 0.699 [0.661, 0.734] | 0.707 | 0.812 [0.784, 0.839] |
| MuRIL base | 0.742 [0.706, 0.778] | 0.713 [0.674, 0.751] | 0.703 | 0.815 [0.788, 0.845] |
| XLM-R base | 0.748 [0.711, 0.782] | 0.705 [0.668, 0.742] | 0.710 | 0.805 [0.774, 0.835] |

Per-class recall for the selected model on Hindi: neutral 0.79 · happy 0.96 · angry 0.65 · fearful 0.73 · **sad 0.59**. On Hindi user turns, sad falls to **0.44** (48 examples).

Notes:
- **The first corpus (v1) leaked** and scored about 0.94: 84% of its test sentences appeared verbatim in training, because EmoInHindi reuses template lines. v2 groups exact and near duplicates (Jaccard ≥ 0.8) into one split. The v1 numbers are void.
- 15% of v2 test sentences still share ≥ 0.7 of their words with some training sentence, which is typical of short everyday sentences.
- The Hinglish test set is machine-transliterated from the Hindi test set. It measures robustness to romanisation, not real Hinglish. Only human-written Hinglish (H6) can.
- English macro-F1 (≈ 0.60) is much lower than UAR (≈ 0.81), because the English test keeps GoEmotions' full neutral share while training was neutral-capped.
- The three encoders' intervals overlap on every language. There is no evidence that one is better.

## Intended use

Research and the local ML demonstration, beside the deterministic pipeline.

## Out of scope — prohibited

- Any product, backend, frontend or mobile use while D-9b is unmet.
- Crisis detection or any safety decision.
- Stating a caller's emotion as a fact.
- Claims of clinical validity.

## Limitations

- EmoInHindi dialogues are scripted and repetitive, and some are bot turns.
- GoEmotions is Reddit English.
- None of the training data is helpline speech or atrocity-victim language.
- Emotion labels are annotators' perceptions, not the speaker's state.
