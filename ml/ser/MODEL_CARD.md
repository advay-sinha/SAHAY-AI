# Model card — speech emotion recognition (SER) candidates

| Field | Value |
|---|---|
| Identity | Plan step M12, decisions D-4, D-5, D-7, D-8, D-10, D-13 and D-14 (EXT-121 to EXT-127) |
| Task | 5 affect classes from a single utterance: `affect:neutral · happy · sad · angry · fearful` |
| Candidates | (1) emotion2vec+ large, frozen: zero-shot 9→5 mapping, and a trained 5-class head on its 1024-d embeddings (primary candidate, as the owner requires). (2) Frozen Whisper Small encoder with a head over learned layer weights. (3) WavLM Base+ fine-tuned: CNN and lower 6 layers frozen, attentive statistics pooling. (4) Prosody logistic regression (interpretable baseline, AE-15). |
| Training data | RAVDESS speech (864 usable clips, 24 actors) and CREMA-D AudioWAV (6,097 usable clips, 91 actors). Acted **English**, studio or near-studio quality. Splits are actor-disjoint and sex-stratified. |
| Inputs | 16 kHz mono, trimmed by Silero VAD; clips with no detected speech (74) are excluded |
| Output | Probabilities over the 5 affect classes. Never a diagnosis, a crisis signal, a band or a score by itself. |
| Weights | Private, beneath `SAHAY_TRAINING_ROOT/ser/runs/`. Never committed, published or redistributed. WavLM derivatives stay private (CC BY-SA 3.0). |

## Status

| Field | Value |
|---|---|
| Feeds D4 | **No.** `ml.acoustics.d4.SER_ENABLED = False`. Under D-8, SER may contribute at most 30% of D4, and only after the promotion gate passes. |
| Model selection | **Pending (R6b):** chosen on 2 held-out team speakers, never on RAVDESS or CREMA-D |
| Promotion gate (R7) | 5-class UAR ≥ 0.45 on the team's Hindi and English gate speakers, no class recall < 0.20, and a neutral negative control. **Not yet run:** it needs human recordings (H5, parked). |
| Victim-facing | Never |
| Crisis pre-check, routing, overrides | Never influenced |

## Measured results (2026-09-26; acted English, unseen actors)

UAR (chance 0.20), with a bootstrap 95% interval where computed (2,000 resamples). CREMA-D test: n = 873 clips, 13 actors. RAVDESS test: n = 141 clips, 4 actors.

| Candidate | Evidence class | Test CREMA-D | Test RAVDESS | Cross-corpus (train CREMA-D → all RAVDESS) |
|---|---|---|---|---|
| emotion2vec+ head | possibly seen in pretraining | 0.784 [0.756, 0.809] | 0.796 [0.721, 0.863] | 0.872 |
| emotion2vec+ zero-shot (forced 5) | possibly seen in pretraining | 0.766 | 0.809 | 0.868 |
| Whisper-encoder head | clean | 0.767 [0.741, 0.794] | 0.784 [0.710, 0.854] | 0.706 |
| WavLM Base+ fine-tune | clean | 0.758 [0.732, 0.783] | 0.758 [0.681, 0.832] | 0.447 (one class recall 0.016) |
| Prosody logistic regression, speaker-normalised | clean | 0.580 [0.549, 0.611] | 0.432 [0.359, 0.509] | 0.487 |
| Prosody logistic regression, pooled | clean | 0.527 | 0.357 | 0.345 |

What these numbers support:
- **The three neural candidates cannot be separated** on acted English: their CREMA-D intervals overlap. Only the prosody baseline is clearly weaker.
- **emotion2vec+'s lead may be memory, not skill.** Its seed stage trained on EmoBox, which is believed to include these corpora, so its high cross-corpus score (0.87) is not clean evidence.
- **WavLM does not transfer across corpora** (0.45). It remains a comparison row.
- **Speaker normalisation helps the prosody baseline** (+0.05 to +0.14), which supports D4's in-session baseline design.
- **"fearful" is the weakest class** for every neural model on CREMA-D (recall 0.49–0.62), and it is the class that matters most here.
- Per-sex UAR differences are 0.03–0.18, measured on 2 actors per sex for RAVDESS, far too few to conclude anything.

What they do not support: any claim about Hindi, Hinglish, Indian accents, telephone audio, distressed rather than acted speech, or clinical relevance. None of that has been measured.

## Intended use

- Research, model selection and the local ML demonstration (shadow display).
- After R7 passes: an auxiliary input to D4, at most 30% of it.

## Out of scope — prohibited

- Victim-facing output of any kind.
- Crisis detection, routing, hard overrides or band decisions.
- Naming an emotion as a fact about a caller on the console. Affect output appears only inside the D4 breakdown, labelled "auxiliary signal, uncalibrated".
- Claims of clinical validity, calibration or production accuracy.

## Limitations

- Acted speech exaggerates emotion, and real distress is often understated.
- English only in training.
- Recording conditions differ from phone calls.
- 74 clips (1%) had no speech detected, most often fearful takes, which may bias the fearful class.

## Retention

Weights and predictions stay beneath the private training root while the experiment is active. If a licence review later refuses a dataset, quarantine the derived weights and record the decision.
