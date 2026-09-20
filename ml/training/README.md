# `ml/training` — EXT-119 MuRIL domain adaptation and the experimental shadow classifier (Task 7)

**This is a private, local hackathon experiment.** It is not an official, independent, clinical
or production evaluation. None of it runs in the product.

- The deterministic pipeline stays authoritative: crisis pre-check, heuristic detectors, SVI
  and routing.
- The trained model, `experimental_shadow_classifier`, runs only in shadow. It cannot change
  routing, crisis handling, evidence links, SVI, D4, guardrails or victim-facing wording.
- Authority: EXT-119 in `docs/EXTERNAL_DECISIONS.md`, including its Invariant 8 clarification.
- Weights derived from the external datasets are for private ML research and the operator-run
  local CLI demonstration only.
- No backend, frontend, mobile or other victim-facing component may ship, import, load or call
  them. Any later backend integration (Task 8) needs its own explicit decision covering
  Invariant 8, licensing, privacy, model behaviour and rollback.

## Three stages

| Stage | Input | Objective | Output |
|---|---|---|---|
| A — domain adaptation | every usable privacy-processed external text window | masked-language modelling, from the pinned MuRIL `afd9f36c…` | domain-adapted encoder |
| B — auxiliary heads (isolated) | external windows whose labels have a documented meaning | one head per source, labels kept as `source:<dataset>:<value>` | diagnostic metrics only; checkpoint never reused |
| C — SAHAY shadow head | private **fictional** records only | multi-label BCE over the 8 schema detector categories | `experimental_shadow_classifier` |

Stage C starts from the Stage A encoder. This was decided in advance, so Stage B's source labels
can never shape the SAHAY head.

## External datasets (EXT-119; licensing and privacy still unresolved)

`python -m ml.data.training_corpus build` builds the corpus. Only this governed builder touches a
dataset.

| Dataset | Records used | Windows | Coverage windows | Duplicate records | Auxiliary task |
|---|---|---|---|---|---|
| Reddit Suicide Detection | 232,072 (2 unreadable rows excluded by Task 5) | 466,055 | 232,072 (first window per record) | 519 | subreddit membership (not a clinical judgement) |
| Dreaddit | 715 | 968 | 968 | 0 | annotated stress (not crisis) |
| EmoInHindi | 1,814 dialogues | 10,861 | 10,861 | 4 | annotated emotions, multi-label (not severity) |
| Hinglish hate-speech derivative | 15,000 labelled + 3,199 unlabelled (MLM only) | 20,151 | 20,151 | 2,912 | hate-speech label (not threat or danger) |
| Hinglish sentiment | 14,569 (25 empty rows excluded by Task 5) | 14,570 | 14,570 | 684 | none: classes 0/1/2 are opaque |
| CREMA-D | 0: all 22,326 local media are Git LFS pointers | — | — | — | unavailable; nothing downloaded |

In total there are 267,369 records in 263,904 duplicate families, making 512,605 windows. Blank
rows, unreadable bytes and LFS pointers are counted, never invented. Every dataset stays
`licence_pending` and every output a `quarantined_research_artifact`. Nothing may be redistributed,
published, uploaded or used commercially.

How the corpus is assembled:
- **Windows.** Text is split into windows of at most 480 characters on word or turn boundaries,
  so each fits a 128-token input.
- **Duplicates.** Task 5 exact and near links, plus identical text across datasets, form duplicate
  families. Each window is weighted `1 / family size`.
- **Partitions.** About 0.5% of families are held out as `mlm_validation`, and about 10% form the
  auxiliary `test` bucket. No family crosses partitions.

**Source labels are never SAHAY labels.** Subreddit membership, stress, emotion, sentiment and hate
speech are never converted into crisis, danger, threat, vulnerability, routing, diagnosis, SVI,
band, D4 or safe/no-alert. The Task 5 label firewall is unchanged: `map_to_sahay` still refuses
everything.

## Stage A schedule

1. **Coverage pass.** One seeded pass over every training window marked `coverage`, so every
   usable record contributes at least its first window.
2. **Balanced continuation.** 40,000 further windows are drawn with dataset-aware sampling, with
   probability proportional to window count to the power 0.3. The suicide corpus falls to about
   45% of draws. Every other window of the long suicide posts can appear here, and nothing is
   discarded to create balance.

Training settings:
- Dynamic 15% masking (80% `[MASK]`, 10% random token, 10% unchanged). Loss is computed only at
  masked positions and weighted per token by duplicate family.
- Maximum 128 tokens, micro-batch 32.
- AdamW at 5e-5, weight decay 0.01, 6% warmup then linear decay, gradient clip 1.0.
- bf16 autocast with fp32 master weights, and seed 20260912.
- No causal or generative objective, and no text is ever reconstructed in a report.

## Stage C: fictional SAHAY supervision

`python -m ml.training.cli fictional` builds the corpus deterministically from a committed bank of
templates written for it.

- **Size.** 110 templates in English, Devanagari Hindi and romanised Hinglish, producing 6,605
  records: 5,005 train, 757 validation and 843 `synthetic_development_test`.
- **Coverage.** Single-turn and multi-turn records, multi-label cases, safe and low-distress
  controls, expected-abstention cases and human-help requests. Also negation, quotation,
  attribution, past events, indirect and conditional wording, misspellings, punctuation and
  spacing, Unicode variants and code-switching.
- **Content limits.** No real names, numbers or identity characteristics. No graphic or procedural
  content.
- **Labels.** Exactly `ml.eval.schema.DETECTOR_CATEGORIES`, in that order, with the schema's own
  definitions.
- **Splits.** By template: a template, every language version and every variant sit in one split.
  Multi-turn records combine templates from one split only.
- **Contamination screen.** Every rendered variant is checked against the exposed fixtures (dev,
  candidates, red-team, and also `locked.json`) for exact, normalised, reordered and verbatim-turn
  matches, high overlap, and a shared distinctive phrase. A hit blocks the whole template family.
  Five families were blocked. They are left out, never reworded to evade the check.
- **Status.** `synthetic_development_test` is a fictional development split from the same
  generator. It is not independent, blind, locked or official.

Model: encoder, attention-masked mean pooling, dropout 0.1, and one linear layer with 8
independent logits (BCE-with-logits). There is no routing, SVI, D4, diagnosis or generative head.
The development threshold is fixed at an uncalibrated 0.5 and never tuned.

Training settings: seeds 13, 42 and 97; early stopping on fictional validation only. There were
two runs, both disclosed:
- **Run 1:** up to 6 epochs, patience 2. It hit the epoch cap while validation was still improving,
  so early stopping never acted.
- **Run 2:** up to 20 epochs, patience 3, with everything else identical (learning rates, loss, 0.5
  threshold). It is the one change that lets the declared early-stopping rule actually decide.

No other setting was searched. The rule below ranks all six seed results from both runs on
validation only.

The selection rule was fixed before training, and applies within each seed and across seeds:
1. higher validation macro F1;
2. higher minimum per-label validation recall;
3. lower validation loss;
4. lower seed or earlier epoch.

## Task 7B: targeted corpus hardening and Stage C retraining

The Task 7 checkpoint stays `rejected_for_product_integration`. Task 7B retrains only the Stage C
head. It reuses the verified Stage A encoder, does not repeat Stage A or Stage B, and adds no
external record to SAHAY-labelled training.

1. **Error analysis** (`cli error-analysis`). This is ID-only: IDs, languages, scripts, labels,
   families, slices, FN/FP families and token statistics, never text. It found that crisis misses
   were mostly Hindi and Hinglish, and concentrated in conditional ("temporal ambiguity"), indirect
   and "disappear" wording. Other families: coercion confused with ordinary disagreement in both
   directions, legal help versus legal urgency, spelling variation and multi-label overlap. After
   this analysis the Task 7 fictional validation and test splits count as exposed development
   material.
2. **Targeted corpus** (`cli hardening-build`, `ml/training/hardening.py`).
   - **Families:** 105 fictional cores in English, Devanagari Hindi and romanised Hinglish. Each
     core carries its contrast family: direct framings keep its label; quoted, reported, past and
     negated framings flip it. Figurative, ordinary-disagreement, general-legal and
     discouraged-help near-misses are their own families. Multi-label records combine two cores
     from one split and record the reason.
   - **Size:** 9,924 records.
   - **Areas:** crisis 34%, coercion 21%, legal 19%, multi-label 13%, controls and other labels 14%.
   - **Languages:** English 35%, Hindi 28%, Hinglish 38%.
   - **Contamination screen:** every record is checked against the Task 7 corpus, every exposed
     fixture file (including `locked.json`) and the private Task 5 hashed keys. Exact, normalised,
     reordered, verbatim-turn and cross-split duplicates block the whole family; near overlap and
     shared token windows are warnings. No private blind corpus is configured.
3. **Freeze before training.** Splits are by family: train 7,492, validation 1,242,
   `synthetic_hardening_holdout` 1,190. The split files, family lists and template bank are hashed
   into a timestamped freeze record, which `cli hardening-verify` re-checks in a fresh process. A
   frozen version cannot be regenerated; a changed holdout needs a new version, with the old one
   marked exposed.
4. **Review packet.** A private sample of every family, label, language, contrast type and
   multi-label combination. Every reviewer field is empty. Human review is not simulated, and it
   is mandatory before any promotion decision.
5. **Predeclared experiment** (`cli stage-c7b-plan`, `ml/training/stage_c7b.py`).
   - **Configurations:** A is BCE with a class-balanced sampler. B is BCE with train-split
     `pos_weight` bounded to [1, 8]. C is focal loss with gamma 2.0.
   - **Schedule:** seed 13 for A, B and C, then seeds 42 and 97 for the configuration that wins on
     validation.
   - **Settings:** micro-batch 16 with accumulation 2 (reducing Task 7's memory spill), at most 20
     epochs, patience 3.
   - **Selection (validation only):** crisis recall, then the minimum recall over crisis, legal and
     coercion, then macro F1, then no-alert specificity, then validation loss, then seed.
   - The plan is hashed before training, and code that no longer matches it refuses to run.
6. **Once-only evaluation** (`cli stage-c7b-evaluate`) on the frozen holdout. It produces the
   promotion gates, the Task 7 comparison on the same holdout, deterministic invariance evidence and
   the contaminated regressions.

**Research gates** for `candidate_for_human_review`. They were fixed in the plan and are never
lowered:
- crisis recall ≥ 0.80, and ≥ 0.70 in each language;
- legal-urgency and coercion recall ≥ 0.70;
- macro F1 ≥ 0.70;
- no-alert specificity ≥ 0.90;
- repeat agreement 1.0;
- no deterministic effect, a prepared review packet, and nothing committed.

Any failed gate keeps `rejected_for_product_integration`. Even a pass gives only
`candidate_for_human_review`, never any product integration.

**Task 7B result.** Configuration C won phase 1 on validation. Selection across all five runs,
still on validation only, picked C with seed 13. On the once-evaluated holdout:
- crisis recall 1.00 in every language, legal-urgency recall 0.73, coercion recall 1.00, no-alert
  specificity 0.92, repeat agreement 1.0;
- macro F1 0.6747 under the existing calculation, below the 0.70 gate. The value covers only the 5
  labels with positive holdout support; immediate danger, isolation and medical urgency are
  excluded as undefined;
- continuing-threat recall 0.11 on its 132 positives.

The checkpoint remains rejected for product integration. It missed the macro-F1 gate, and full
eight-label promotion evaluation was not possible because three labels had no positive holdout
support (`full_label_coverage: false`, `promotion_metrics_fully_evaluable: false`). No promotion
conclusion can be made for those three labels, and human review remains pending. See
`ml/shadow/MODEL_CARD.md`. The gates were not lowered, no configuration was added after seeing
results, and the frozen holdout was not changed.

**Metric-validity correction** (`cli stage-c7b-correct`). Every per-label metric now reports its
denominator: precision TP+FP, recall TP+FN, specificity TN+FP. A zero denominator gives `null`
with a reason, never 0. Macro averages list the labels they include and exclude. Label coverage
(positive and negative support per label) is part of every report, and a report without full
coverage can never yield `candidate_for_human_review`. The correction reads the stored per-label
counts of the once-only evaluation. It re-predicts nothing, leaves the original report and the
frozen holdout byte-identical, and keeps the previous status file as `STATUS.pre-correction.json`.

## Three evidence classes, reported separately

- **A. External auxiliary evidence:** masked-language validation loss and perplexity, and Stage B
  source-namespace metrics. These are never SAHAY safety metrics.
- **B. Synthetic development evidence:** micro and macro precision, recall and F1, per-label
  counts, specificity, by-language results, exact match and Hamming loss at the fixed 0.5, and
  repeat determinism. This is fictional data, so it says nothing about real-world performance.
- **C. Contaminated exposed regression:** run once, after selection, on the published dev,
  candidate and red-team victim-input fixtures, next to the deterministic pipeline. These are
  never used to train, stop early, pick a threshold, pick a seed or pick a checkpoint. `locked`,
  blind and frozen corpora are never evaluated.

Measured values stay in the private reports beneath `SAHAY_TRAINING_ROOT/reports/`. They are
summarised in the Task 7 report, never as official numbers.

## Commands

These run in the private model environment. All are offline with sockets blocked, and none has a
default path.

```text
SAHAY_DATASETS_ROOT, SAHAY_MODELS_ROOT, SAHAY_TRAINING_ROOT   (explicit; refused if inside a SAHAY checkout)

python -m ml.data.training_corpus build --ext119-local-training --acknowledge "<EXT-119 sentence>"
python -m ml.training.cli preflight
python -m ml.training.cli fictional
python -m ml.training.cli stage-a
python -m ml.training.cli stage-b
python -m ml.training.cli stage-c --seeds 13 42 97 --tag run1
python -m ml.training.cli stage-c --seeds 13 42 97 --epochs 20 --patience 3 --tag run2
python -m ml.training.cli verify-shadow
python -m ml.training.cli error-analysis
python -m ml.training.cli hardening-build
python -m ml.training.cli hardening-verify
python -m ml.training.cli stage-c7b-plan
python -m ml.training.cli stage-c7b --phase 1
python -m ml.training.cli stage-c7b --phase 2
python -m ml.training.cli stage-c7b-select
python -m ml.training.cli stage-c7b-evaluate
python -m ml.training.cli task7b-retention
python -m ml.training.cli stage-c7b-correct
python -m ml.shadow.demo --checkpoint-set task7b text --example 4
python -m ml.training.cli regression
python -m ml.shadow.demo examples
python -m ml.shadow.demo text --example 1
python -m ml.shadow.demo voice --synthetic silence --language hi
```

The default test suite needs none of this: no GPU, no model, no dataset.

## Shadow-mode boundary and the local demonstration

`ml.shadow.demo` is an operator-run CLI. It has no server, listener, upload, database write or
written file, and it never echoes an input or a transcript.
- **Typed text** is refused if it reproduces an external training record. The check uses private
  hashed keys, never the text.
- **Voice** runs only through `GatedTranscriber`: Silero VAD, then validated intervals, then
  Whisper. Whisper is skipped when no speech is found.
- **ASR hallucination risk remains.** Task 6 showed Whisper producing fluent text from
  non-speech. A VAD false positive, such as a speech-like synthetic signal, still reaches
  Whisper.
- **Output.** The deterministic result is printed as the authority, with D4 unavailable. The
  shadow probabilities and fixed-0.5 development firings are printed beside it as experimental,
  with agree/disagree flags. The demo never shows a "safe" verdict, a diagnosis, clinical advice,
  a routing decision or SVI chosen by the model, D4 from the model, or a source-dataset label.

## Prohibited claims

Never describe this model as production-ready, authoritative, clinically validated,
independently evaluated, calibrated or safe. Never quote its synthetic or regression numbers as
accuracy on real victims, and never present a source label as safety ground truth.

## Retention and deletion

Everything lives beneath `SAHAY_TRAINING_ROOT`: corpora, the exact-key file, checkpoints,
optimiser state and reports.

- **Keep** it only while the experiment is actively needed.
- **Delete** a directory to remove what it holds. Nothing is deleted automatically.
- **If a licence or privacy review refuses a dataset**, quarantine every checkpoint derived from
  it (Stage A, B and C) and stop using it. Record whether it will be deleted or retrained without
  that dataset in the decision log.
- **Never commit** any of it.
