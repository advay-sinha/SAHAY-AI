# Model card — `experimental_shadow_classifier`

| Field | Value |
|---|---|
| Identity | `experimental_shadow_classifier`: experimental shadow output only, development-only, uncalibrated, not clinically validated, not independently evaluated, never authoritative |
| Decision | EXT-119 (`docs/EXTERNAL_DECISIONS.md`), including its Invariant 8 clarification |
| Base | `google/muril-base-cased` at `afd9f36c7923d54e97903922ff1b260d091d202f` (Apache-2.0), domain-adapted locally by masked-language modelling (Stage A) |
| Head | One linear layer over attention-masked mean pooling, with 8 independent logits (sigmoid, BCE-with-logits) |
| Label order | `crisis_self_harm`, `immediate_danger`, `continuing_threat`, `medical_urgency`, `isolation_boycott_displacement`, `legal_urgency`, `communication_safety_coercion`, `explicit_human_request` (exactly `ml.eval.schema.DETECTOR_CATEGORIES`) |
| Threshold | Fixed at 0.5 for development reporting; uncalibrated and never tuned |
| Input | Victim turns only, joined in order; at most 128 tokens; English, Devanagari Hindi, romanised Hinglish |
| Output | A probability and a development firing per label, `calibrated: false`, `authoritative: false`. No routing, band, SVI, D4, diagnosis, safe verdict or source label |
| Weights | Private, beneath `SAHAY_TRAINING_ROOT` (safetensors). Never committed, published, redistributed or uploaded |

## Status (Task 7 accepted as an experimental result, 2026-09-12)

| Field | Value |
|---|---|
| `deployment_status` | `rejected_for_product_integration` |
| `backend_integration_allowed` | `false` |
| `frontend_integration_allowed` | `false` |
| `mobile_integration_allowed` | `false` |
| `victim_facing_allowed` | `false` |
| `shadow_local_demo_only` | `true` |
| Crisis recall of the selected private checkpoint | 0.23 on fictional validation; 0.46 on the fictional `synthetic_development_test` (fixed 0.5, uncalibrated) |
| Against the deterministic pipeline | The deterministic pipeline substantially outperformed it on the exposed regression fixtures: micro F1 0.91 against 0.68 on dev, and 0.87 against 0.70 on candidates (contaminated evidence) |
| Crisis pre-check | This checkpoint must not replace, supplement or influence the crisis pre-check |
| Promotion threshold | None: no numeric promotion threshold has been approved |
| Promotion path | Promotion requires all three: a richer human-reviewed fictional corpus, a new training and evaluation task, and a separate explicit integration decision |

## Training data

- **Encoder adaptation (Stage A).** Every usable privacy-processed text record of five external
  datasets: Reddit Suicide Detection, Dreaddit, EmoInHindi, the local Hinglish hate-speech
  derivative and Hinglish sentiment. Their licensing and privacy approval are **unresolved**; they
  stay `licence_pending` and quarantined research artefacts. Some may contain authentic personal
  narratives, and redaction does not catch names or contextual identifiers.
- **SAHAY head (Stage C).** Only private fictional development records produced by a committed
  template generator. They are screened against every exposed SAHAY fixture, and a matching
  template family is blocked.
- **Source labels.** No external source label was used as a SAHAY label. Stage B auxiliary heads
  were isolated diagnostics and never initialised or touched this model.

## Intended use

- Private ML research.
- An operator-run local CLI demonstration (`python -m ml.shadow.demo`) that shows this model's
  shadow output beside the authoritative deterministic pipeline.

## Out of scope — prohibited

- Any backend, frontend, mobile or other victim-facing component shipping, importing, loading or
  calling these weights. Task 8 integration needs a separate explicit decision covering
  Invariant 8, licensing, privacy, model behaviour and rollback.
- Changing routing, escalation, crisis handling, evidence links, SVI, D4, guardrails or
  victim-facing wording.
- Claims of production readiness, clinical validity, calibration, independent or official
  evaluation, or safety certification.

## Evidence and its limits

- **Synthetic development metrics** come from a fictional split made by the same generator. They
  show that the head learned the generator's patterns, **not** how it behaves on real speech or
  real text.
- **Exposed-regression numbers** on the published dev, candidate and red-team fixtures are
  **contaminated**. They were computed once, after selection, and never used for any choice.
- **Never evaluated** on the locked, blind or any frozen independent corpus. The locked count
  stays 0.
- **Voice input** carries Whisper's hallucination risk. The VAD gate stops silence and tones but
  not a VAD false positive.
- **No calibration.** The 0.5 threshold is a convention, not an operating point.

The measured values are in the Task 7 report and the private reports beneath
`SAHAY_TRAINING_ROOT/reports/`.

## Retention

- Keep the weights only while the experiment is actively needed.
- If a licence or privacy review refuses any Stage A dataset, quarantine these weights. Record the
  decision to delete or retrain in the decision log.
- Nothing is deleted automatically.
