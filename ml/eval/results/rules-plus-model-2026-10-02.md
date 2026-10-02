# Rules, model, and rules-plus-model on the labelled fixtures (2026-10-02)

**Evidence class: regression on published development fixtures.** The locked set has 0 samples, so
nothing here is an official or independent result. Small samples: treat as indicative only.

Model: task7b experimental shadow classifier (MuRIL encoder), checkpoint C-seed-13, status
`rejected_for_product_integration`, firing threshold 0.5. Rules: the deterministic pipeline
(`ml.eval.predict`). "Either" fires when the rules or the model fire (the PC-14 review flag).

| Label | Split | Rules P / R | Model P / R | Either P / R |
|---|---|---|---|---|
| crisis_self_harm | dev | 0.636 / 1.0 | 0.412 / 1.0 | 0.35 / 1.0 |
| communication_safety_coercion | dev | 1.0 / 0.857 | 0.444 / 0.571 | 0.545 / 0.857 |
| legal_urgency | dev | 1.0 / 1.0 | 0.571 / 0.444 | 0.75 / 1.0 |
| crisis_self_harm | candidates | 0.8 / 0.889 | 0.562 / 1.0 | 0.5 / 1.0 |
| communication_safety_coercion | candidates | 1.0 / 0.6 | 0.375 / 0.6 | 0.5 / 1.0 |
| legal_urgency | candidates | 1.0 / 0.857 | 0.571 / 0.571 | 0.7 / 1.0 |

Model-only firings (model fired, rules did not): dev 17, all wrong; candidates 19, of which 4 were
real cases the rules missed (1 crisis, 2 coercion, 1 legal urgency).

Reading: on the candidate set, adding the model as a review flag recovered every case the rules
missed, at the cost of roughly one false flag for every two messages flagged. On the development
set it added only false flags. This supports the PC-14 design: the model may ask an officer to
review, and may never act on its own. Reproduce with the private model environment and
`SAHAY_TRAINING_ROOT` set; the measurement script is not part of the default path.
