# Model card — `experimental_weak_shadow_classifier` (Stage W, plan M14)

| Field | Value |
|---|---|
| Identity | Shadow output only: development-only, uncalibrated, trained partly on source labels that are not SAHAY ground truth, not clinically validated, never authoritative |
| Decisions | EXT-129 (dataset use for MVP training and validation) and its 2026-09-28 Stage W notes, including the official Dreaddit re-download |
| Base | Stage A domain-adapted MuRIL (`run-20260912-054730`) |
| Network | Attention-masked mean pooling, dropout 0.1, one linear layer with 9 independent logits: the 8 schema detector categories plus `d5_text_distress` |
| Loss | Masked focal loss (gamma 2). A weak row supervises only its own logit; fictional rows supervise the 8 detector logits, with D5 masked |
| Threshold | Fixed 0.5; never tuned |
| Selected checkpoint | **W2, seed 13, epoch 8**, chosen by the predeclared rule on fictional validation only |
| Weights | Private, beneath `SAHAY_TRAINING_ROOT/stage-w/checkpoints/`. Never committed, published or loaded by a product component |

## Status

| Field | Value |
|---|---|
| Deployment | **Shadow only.** `rejected_for_product_integration`. |
| Feeds SVI, D5, D4, routing, crisis handling, evidence | **No** |
| Victim-facing | Never |
| Promotion path | A reviewed locked set, a separate integration decision and the leads' approval. None exists. |

## Training data

| Source | Target | Train (windows, 0 / 1) | Test bucket (0 / 1) | Caveat |
|---|---|---|---|---|
| Task 7B fictional corpus `7b-v1` | 8 detector labels | 7,492 records | holdout: 1,190 records | synthetic, agent-generated |
| Reddit Suicide Detection | `crisis_self_harm` | 10,000 / 10,000 | 3,000 / 3,000 | subreddit of origin, not a human judgement |
| Hate-speech derivative (English rows) | `continuing_threat` | 8,090 / 7,210 | 911 / 741 | hate speech is not a threat |
| Dreaddit, official archive | `D5` → `d5_text_distress` | 1,787 / 2,055 | 463 / 505 | crowd-annotated stress; not trauma or a diagnosis |

Each epoch uses the whole fictional train split plus a weak draw of equal size, shared equally across the arm's weak targets.

## Results (2026-09-28; one run per arm at seed 13, plus seeds 42 and 97 for W2)

| Run | Validation macro F1 (selection) | Fictional holdout macro F1 | Holdout crisis recall hi / Hinglish | Weak-test AUROC: crisis / threat / D5 | Exposed micro F1, dev / candidates |
|---|---|---|---|---|---|
| W0 (fictional only) | 0.538 | 0.680 | 0.756 / 0.734 | 0.841 / 0.405 / 0.534 (D5 not trained) | 0.527 / 0.482 |
| W1 (+ crisis, D5) | 0.578 | 0.751 | 0.967 / 0.917 | 0.993 / 0.358 / 0.797 | 0.508 / 0.575 |
| **W2 (+ threat), seed 13 — selected** | **0.628** | **0.733** | **0.944 / 0.835** | **0.993 / 0.920 / 0.830** | **0.595 / 0.584** |
| W2, seed 42 | 0.608 | 0.842 | 0.978 / 0.982 | 0.995 / 0.914 / 0.824 | 0.518 / 0.475 |
| W2, seed 97 | 0.626 | 0.788 | 0.856 / 0.752 | 0.993 / 0.910 / 0.822 | 0.495 / 0.553 |
| Deterministic rules | — | — | — | recall 0.376 / 0.003 / 0.099 on the same windows | **0.933 / 0.881** |

### Evidence classes

| Result | Evidence class |
|---|---|
| Fictional holdout | Synthetic development. `immediate_danger`, `medical_urgency` and `isolation_boycott_displacement` have no positive holdout support, so they are excluded as undefined. |
| Weak test buckets | Weak supervision from source labels |
| Exposed fixtures | Contaminated regression |
| Probes | Descriptive only |

### Findings

- **Weak supervision works on text like its sources.**
  - Crisis AUROC rises from 0.84 (W0) to 0.99.
  - The D5 logit reaches AUROC about 0.82. Rule-based D5 finds only 0.10 of the stressed posts, at precision 0.81.
  - Threat rises from 0.40 to 0.92, and only in W2.
- **Hindi and Hinglish crisis recall on the fictional holdout improves**, from 0.76 and 0.73 (W0) to 0.94 and 0.84 (W2 seed 13). This happens even though every weak source is English.
- **Seed variance is large.** W2's holdout macro F1 spans 0.733–0.842 across seeds. W1 (0.751) and W2 cannot be told apart.
- **On SAHAY fixtures the model is far weaker than the rules.**
  - Micro F1 is 0.60 against 0.93 on dev, and 0.58 against 0.88 on candidates.
  - The model has 25 and 18 false positives.
  - The deterministic pipeline stays authoritative.
- **It catches some things the rules miss.** On candidates, 5 fixture-labels are caught only by the model:
  - `CAND-EN-003` crisis: the indirect method-and-plan statement (P-DET-4);
  - `CAND-EN-004` threat and coercion;
  - `CAND-EN-005` medical;
  - `CAND-HG-012` legal.

  On dev, 1 is caught only by the model (`DEV-HI-011` threat).
- **Indirect-wording probes are not specific.**
  - The selected model fires on 6 of 7 indirect crisis probes. The crisis pre-check fires on 0 of 7.
  - But it also fires on **all 3 non-crisis controls**, such as travelling tomorrow.
  - It reads absence or sadness as crisis. It is not usable as a crisis signal; the crisis pre-check stays the only crisis authority.
- **Red-team victim inputs:** the model agrees with the expected crisis outcome on 8 of 8. The rules also agree on 8 of 8.

## Interpretable baseline (AE-15, 2026-09-29)

A standard-library logistic regression (`ml/training/baseline_lr.py`) was trained on the same data and scored by the same evaluator:

| Run | Fictional holdout macro F1 | Weak-test AUROC: crisis / threat / D5 | Exposed micro F1, dev / candidates |
|---|---|---|---|
| LR-W0 | 0.477 | 0.615 / 0.530 / (not trained) | 0.244 / 0.290 |
| LR-W2 | 0.497 | 0.935 / 0.801 / 0.762 | 0.477 / 0.373 |
| MuRIL W2 (selected) | 0.733 | 0.993 / 0.920 / 0.830 | 0.595 / 0.584 |
| Deterministic rules | — | — | 0.933 / 0.881 |

- **MuRIL beats the linear model everywhere**, by 0.24 macro F1 on the holdout and 0.12–0.21 micro F1 on the exposed fixtures.
- **Both models are far below the rules** on SAHAY fixtures.
- **The borrowed labels help the linear model too.** Its crisis AUROC rises from 0.61 to 0.94.

## Corpus shortcut found by the baseline

The linear model's strongest features for crisis and coercion were fragments of `[SEP]`, the marker that joins turns in a multi-turn record. The Task 7B corpus explains why:

| Split | Multi-turn records with at least one risk label | Crisis rate, multi-turn vs single-turn | Coercion rate, multi-turn vs single-turn |
|---|---|---|---|
| Train | **911 of 911** | 0.51 vs 0.25 | 0.50 vs 0.15 |
| Holdout | **182 of 182** | 0.54 vs 0.20 | 0.49 vs 0.13 |

"Has several turns" therefore predicts "has a risk label" in both training and holdout.

The multi-label records are built by combining two cores, so none is all-negative.

## Corpus 7b-v2 and what the shortcut actually cost (R10, 2026-09-29)

`7b-v2` keeps every `7b-v1` record and adds one-positive and all-negative two-turn records. In training data, multi-turn records now carry a risk label 0.62 of the time, against 0.62 for single-turn.

**Per-label rates are only partly balanced:**

| Label | v1, multi vs single | v2, multi vs single |
|---|---|---|
| Crisis | 0.51 vs 0.25 | 0.29 vs 0.25 |
| Coercion | 0.50 vs 0.15 | 0.25 vs 0.15 |
| Legal | 0.38 vs 0.13 | 0.21 vs 0.13 |

That's why the logistic baseline still ranks `[SEP]` first even on v2.

**Retrained on v2:**
- Arms W0, W1 and W2 were retrained with seeds 13, 42 and 97, the last two for the winner.
- The predeclared validation rule selected **W0 seed 13** (validation macro F1 0.658). W0's other seeds reached 0.547 and 0.493, so seed variance is large.

**Cross-check** (`python -m ml.training.cli shortcut-check`): both generations of checkpoints, scored on the v2 holdout by record kind. Evidence class: synthetic development.

| Checkpoint | Single-turn macro F1 | Two-positive multi-turn F1 | **One-positive multi-turn F1** | False alarms on all-negative single-turn | **False alarms on all-negative multi-turn** |
|---|---|---|---|---|---|
| v1 W0 s13 | 0.638 | 0.737 | 0.343 | 2.3% | 2.4% |
| v1 W2 s13 (v1 selected) | 0.696 | 0.787 | 0.422 | 3.8% | 2.4% |
| v2 W0 s13 (v2 selected) | 0.696 | 0.758 | 0.691 | 7.8% | 17.4% |
| v2 W2 s13 | 0.743 | 0.785 | **0.790** | 3.8% | 7.8% |

What this shows (it corrects the earlier expectation):
- **MuRIL did not learn the crude shortcut.** v1 checkpoints raise false alarms on only 2.4% of harmless multi-turn records. The linear baseline did lean on `[SEP]`; MuRIL did not.
- **The real v1 gap was mixed multi-turn records.** On "one risky turn plus one harmless turn", v1 checkpoints reach only 0.34–0.42 macro F1, against 0.69–0.79 after v2 training.
- **v2 training costs some false alarms**, more for W0 than W2 (17.4% against 7.8% on harmless multi-turn records).
- **On SAHAY's exposed fixtures nothing changed materially.** Micro F1 for the v2 selected W0 is 0.56 (dev) and 0.62 (candidates), against 0.60 and 0.58 for the v1 selected W2. Rules: 0.93 and 0.88.
- **The logistic baseline** on v2 scores 0.44 (LR-W0) and 0.48 (LR-W2) holdout macro F1, and 0.20–0.49 exposed micro F1.

Verdict: unchanged. The shadow detector stays a second opinion only. A future `7b-v3` could match per-label rates, not only the overall rate. `7b-v1` and `7b-v2` both stay frozen.

**Untrained D5 head in W0 arms.** W0 never trains `d5_text_distress`. Its output sits near 0.5, so at the fixed ≥ 0.5 threshold it "fires" on everything. Its D5 recall (0.81 for MuRIL W0, 1.0 for LR-W0) is meaningless and is left out of the table.

## What this supports

A shadow second opinion shown next to the deterministic result in the local ML demonstration. It is worth considering later for P-DET-4 (a `possible_indirect_risk` flag that routes to a person, never to Critical) once a reviewed locked set can measure its false-positive rate.

## What it does not support

- Any claim about real helpline speech.
- Replacing or supplementing the crisis pre-check.
- Using the D5 logit in the SVI.
- Any clinical claim.
- Any claim that W2 is better than W1, given the seed spread.

## Limitations

- Every weak source is English web text. Its labels are proxies, not SAHAY definitions.
- The fictional holdout comes from the same generator family as training.
- The exposed fixtures are published, so they are regression evidence only.
- The probes were written by the author and are unreviewed.
