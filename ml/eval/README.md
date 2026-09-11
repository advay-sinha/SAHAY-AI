# ml/eval — deterministic safety and vulnerability evaluation

This harness evaluates the text-first pipeline honestly. Everything here is fictional, deterministic and offline:

- no LLM, no network, no model download, no training, no audio;
- no Torch or Transformers;
- no new dependencies (Python standard library only).

Nothing here is clinically or linguistically validated. The numbers are development numbers until real human reviews exist; see "Split discipline" below.

## Commands

Run everything from the repository root.

```powershell
# Fast suite, including the evaluation-framework tests
python -m unittest discover -s ml/tests -t .
python -m pytest ml -q

# The full evaluation (all splits, red-team, SVI sensitivity, reproducibility checks)
python -m ml.eval.run_eval                       # writes runtime/eval/eval-all.{json,md}
python -m ml.eval.run_eval --corpus dev          # one split: dev | candidate | locked
python -m ml.eval.run_eval --out ml/eval/results --tag baseline-2026-09-11

# Safety-hardening report (baseline, exposed-regression, candidate, locked, remaining failures)
python -m ml.eval.hardening_report               # writes ml/eval/results/safety-hardening-2026-09-11.{json,md}
python -m ml.eval.hardening_report --out runtime/eval

# Regenerate the corpora from the authoring tables, or check they are not stale
python -m ml.eval.build_corpus
python -m ml.eval.build_corpus --check
```

`run_eval` exits with status 1 if any of these fail:
- schema validation
- split disjointness
- the identifying-data scan
- the offline/import guard
- determinism
- replay consistency

Metric values themselves never change the exit status. A bad number is still reported, not hidden behind a failure code.

## Layout

| File | Purpose |
|---|---|
| `schema.py` | Label schema **1.0.0**: categories, sample shape, review rules, lock eligibility, identifying-data scan |
| `build_corpus.py` | Authoring tables, which generate `corpus/*.json` |
| `corpus/dev.json` | Development fixtures. Tuning allowed. |
| `corpus/candidates.json` | Evaluation candidates. Never used for tuning. All `pending_review`. |
| `corpus/locked.json` | Locked evaluation set. **Empty** until real reviews are recorded. |
| `corpus/redteam.json` | Guardrail red-team cases |
| `predict.py` | Runs the real pipeline (`crisis_check`, `assess`, `match_turn`) and maps its output to categories |
| `evaluate.py` | Confusion counts, P/R/F1/specificity, slices, routing, evidence, abstention, bands, D4 |
| `metrics.py` | Arithmetic. Undefined metrics are `None` and reported as `n/a`, never 0 or 1. |
| `redteam.py` | Red-team runner and prohibition coverage |
| `svi_sensitivity.py` | Analysis of the frozen SVI (reads it, never changes it) |
| `checks.py` | Determinism, scenario replay, LLM-off walk, offline/network/import guard |
| `AUDIT.md` | Capability-by-capability audit of the pipeline |
| `PROPOSALS.md` | Proposed contract, guardrail and dependency changes. None of them is implemented. |
| `results/` | Committed reports: the baseline (never rewritten) and the safety-hardening report |
| `CONTAMINATION.md`, `contamination.py` | Ledger and registry of every fixture whose outcome has been published. Results on those fixtures are regression performance only. |
| `corpus/redteam_hardening.json` | Near-miss and paraphrase cases written by the rule author alongside the output rules. Development evidence, not holdout. |
| `hardening_report.py` | Before/after report that reads the baseline and never rewrites it |
| `reviews/` | Human safety-review packets. Review records are filled in only by the reviewers themselves. |
| `review_workflow.py`, `reviews/fixture_reviews.jsonl` | Fixture-level review: export packets, validate and import human records into the append-only, SHA-256 hash-chained ledger (each record once; `validate-ledger` checks the chain), and report lock eligibility. It never writes `locked.json`. |

## Label schema 1.0.0

The category definitions are in the `schema.py` docstring. Each sample records:
- a stable ID (`DEV-EN-001`, `CAND-HG-004`, `LOCK-HI-002`);
- `language`: `hi`, `en` or `hinglish`;
- `channel`;
- fictional turns (`t1`, `t2`, ...);
- one boolean per category;
- `expected_evidence`, the turn IDs behind each positive detector category;
- `expected` values: `crisis_precheck`, `routed_critical`, `abstain` (`true`, `false` or `null`), and `band` (a band or `null`);
- review status and reviewers;
- `schema_version`;
- notes for difficult cases.

Labels describe what the text **means**, never what the system currently does. The `expected` block encodes policy. For example, a crisis phrase that is only quoted in someone else's words has `crisis_self_harm = false`. If someone tells the victim to kill themself, recall-first routing to a person is still expected; that case sits in the notes.

### How each category is measured

| Category | Signal the system is judged on |
|---|---|
| `crisis_self_harm` | The synchronous crisis pre-check fires on the turn |
| `immediate_danger` | A D1 tier-3 (imminent presence) lexicon match |
| `continuing_threat` | Any D1 match, or a D3 match of tier 2 or above |
| `medical_urgency` | A D7 match of tier 2 or above (pain alone is tier 1) |
| `isolation_boycott_displacement` | Any D6 match |
| `legal_urgency` | Any D8 match |
| `communication_safety_coercion` | Any D9 match, or evidence behind the coercion alert |
| `explicit_human_request` | **Excluded.** There is no text detector; the app sends `request_human` from a button. |
| `negated_risk_language`, `quoted_attributed_risk`, `adversarial_injection` | Slice labels. Metrics are cut by them. |

- **Critical miss:** `expected.routed_critical` is true, but the case was neither caught by the pre-check nor banded Critical.
- **False escalation:** the case was routed Critical when `expected.routed_critical` is false.

## Split discipline and review

- **dev.** May be used to implement and tune. The clause-scoped crisis negation (`AUDIT.md`) was motivated only by dev fixtures.
- **candidate.** Never used for tuning. Two candidate labels were revised before any review, to follow the clarified coercion definition. The notes say so, and both revisions make the system look *worse*, not better.
- **locked.** The only split whose numbers are official. A sample is lock-eligible only when:
  - its status is `approved`, and
  - it has real, dated approvals from distinct GitHub users: **two** for crisis or immediate-danger samples, one otherwise.

  `TODO-reviewer-N` placeholders never count. The locked set is empty, so **official critical-safety metrics are pending**.

### The independent evaluation set does not exist yet

The five corpora in `corpus/` are all exposed: dev was tuned on, and every candidate and red-team
outcome was published in `results/`. They remain the regression and development corpora and their
numbers are regression performance, not evaluation performance.

An independent number needs samples that nobody involved in building the pipeline has seen, which
means humans must write them. The infrastructure for that is `ml/eval/blind/` plus the two commands
`python -m ml.eval.blind_corpus` and `python -m ml.eval.blind_evaluation`; read
**[`BLIND_EVALUATION.md`](BLIND_EVALUATION.md)** first, then `blind/AUTHOR_INSTRUCTIONS.md`,
`blind/REVIEWER_INSTRUCTIONS.md` and `blind/STAFFING.md`.

The corpus lives outside Git under `SAHAY_EVAL_ROOT`. No module in `blind/` can load a prediction
module before freeze, and no command authors a sample or fills a human record. The post-freeze
measurement path is implemented: it verifies the freeze manifest, every file hash and every ledger
head, then reuses `predict`, `evaluate`, `metrics`, `checks` and `redteam` — nothing is
re-implemented — and publishes a complete result outside Git. The first run on a corpus is labelled
`independent_evaluation` and exposes it; every later run needs `--regression` and can never
overwrite the first.

`blind_evaluation run` still refuses today, with exit code 12, because nothing has been frozen.
Locked count remains 0 and official metrics remain unavailable until the human authoring and review
described there is done.

### Reviewer checklist, to be completed by a person and never by Claude

For each candidate:

1. The text is fictional. It contains no real name, place, phone number, address, case number or narrative.
2. Every category label matches its definition in `schema.py`, including negated and quoted language.
3. `expected_evidence` names exactly the turns that carry each positive label.
4. The `expected` values (pre-check, Critical routing, abstention, band) are what a trained helpline officer would want.
5. For crisis and immediate-danger samples: two reviewers from the safety and helpline side, working independently, with any disagreement adjudicated and noted.
6. Record `{"reviewer": "<github-username>", "decision": "approve" | "reject", "date": "YYYY-MM-DD"}`, set `status`, then move the sample to `LOCK-...` in `build_corpus.py`.
7. Never tune a detector on a locked sample. If a locked sample shows a defect, write a new dev fixture for the fix.

## Known-failure ledger

- Red-team failures are listed in `KNOWN_REDTEAM_FAILURES` in `ml/tests/test_eval.py`. A new failure fails the suite. So does a recorded failure that silently starts passing: when you fix one, remove it from the ledger in the same change.
- Critical misses and false escalations are listed by fixture ID in every report.
