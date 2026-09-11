# Proposal — a future D4 (acoustic distress) evaluation experiment — PROPOSAL ONLY

**Status:** not approved and not implemented. D4 remains **unavailable**:
- on text channels it is structurally unavailable (PC-08, renormalised);
- on voice channels it is missing, so the assessment abstains.

This change generates no D4 value and substitutes no zero. It maps no emotion to vulnerability, invents no acoustic confidence and leaves PC-08 untouched.

## Why nothing can be done today

- No audio dataset is approved. Common Voice Hindi, RAVDESS and CREMA-D are PROPOSED or pending in the registry.
- The local EmoInHindi archive is **text**, not audio (ZIP directory: 1 CSV and 1 Markdown file, no member with an audio extension; contents not read).
- No acoustic model is approved: EXT-004 (faster-whisper) and EXT-005 (Silero VAD) are PROPOSED.
- Emotion labels (acted or annotated) are not distress labels. Distress is not vulnerability. Neither is a clinical finding.

## Experiment design (for approval by the AI/ML and Safety and Backend leads, and contract review)

| Item | Proposal |
|---|---|
| Task definition | Estimate *audible acute distress in the caller's voice right now* (for example trembling, crying or panic in the voice), as one input to D4. It is not an emotion classifier, not a mental-state inference and never a diagnosis. |
| Permitted labels | `audible_distress: none / some / strong / cannot_tell`, per utterance, from trained human listeners, with a `cannot_tell` option and an audio-quality flag. |
| Labels never to be read clinically | Any acted-emotion category ("sad", "fear", "anger"), depression, anxiety, PTSD, "hysteria", deception, stress scores from text datasets. None may be shown to a victim. |
| Data | Only approved datasets (`approved_for_evaluation` or higher in `ml/data/registry/datasets.json`), plus consented, fictional, scripted SAHAY recordings. Acted corpora are for auxiliary pre-training only, never for validation claims. |
| Speaker-independent splits | No speaker in more than one split. Splits are fixed and logged before any model is scored. The locked split is reviewed at fixture level (two reviewers for any safety-critical item). |
| Language slices | Hindi, English, Hinglish/code-switched, and at least one further Indian language before any claim of multilingual support. Metrics are reported per slice and never averaged away. |
| Noise and device slices | Quiet versus noisy; phone microphone versus headset; codec or compression level; far-field. Poor audio must trigger abstention, not a low score. |
| Calibration | Reliability curves and expected calibration error per slice. A calibrated confidence is the *only* confidence that may reach `svi.compute`. |
| Abstention | Low audio quality, low confidence or out-of-distribution voice produces `needs_human`. Silence or a missing measurement is never treated as "no distress". |
| Fairness checks | Error rates by gender presentation, age band, dialect or region and language, with a documented maximum gap. Caste, religion and region must never be inferred. |
| False-positive risks | Crying can be relief; a loud voice can be a normal speaking style; accent and dialect can be misread as distress. A false positive over-prioritises a case; a false negative under-prioritises one. Both must be measured. |
| Human-assessment fallback | The officer always hears the audio and decides. D4 is advisory, with an evidence timestamp and a quality flag. A crisis on the text path still interrupts unconditionally. |
| Backend integration boundary | D4 arrives only through the assessment runner as `{score, confidence, evidence_turn_ids, quality}`. It is never sent to the victim socket (the fan-out allowlist) and never shown to victims. |
| Required approvals | An EXT decision for each dataset and model. A contract change (CONTRACTS §5 and §7) if the D4 fields or PC-08 behaviour change. A `type:dialogue` review for any victim-facing effect. A fixture-level locked-set review before any metric is official. |

## Exit criteria before D4 may carry a non-null value

1. An approved dataset and model decisions exist.
2. A locked, speaker-independent, reviewed evaluation set exists.
3. Per-slice calibration and fairness reports meet documented thresholds.
4. Abstention works on poor audio.
5. The leads approve a contract update.

Until then, D4 stays unavailable.
