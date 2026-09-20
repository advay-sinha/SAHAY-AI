# Blind human-authored evaluation corpus

**Status on 2026-09-11: no official sample exists. Locked count 0. Official metrics unavailable.**
This document and the tooling under `ml/eval/blind/` are the infrastructure humans need in order
to build an independent evaluation set. The corpus itself has not been written, and no part of it
may be written by Claude, ChatGPT, another language model, or the code agent that built this
tooling.

That zero is the correct outcome of this phase, not a failure of it. What follows is what exists,
what it refuses to do, and exactly what human work is still required.

---

## 1. Why the existing corpora cannot produce an independent number

| File | Samples | Why it is exposed |
|---|---|---|
| `ml/eval/corpus/dev.json` | 57 | Development split. Tuned on. Never holdout by design. |
| `ml/eval/corpus/candidates.json` | 48 | Every outcome, pass and fail, was published in `results/eval-baseline-2026-09-11.json`. |
| `ml/eval/corpus/redteam.json` | 39 | Every outcome published. |
| `ml/eval/corpus/redteam_hardening.json` | 75 | Written alongside the rules they test. |
| `ml/eval/corpus/redteam_urgency.json` | 29 | Written alongside the rules they test. |

Beyond publication, 13 candidate, 8 dev and 19 red-team fixtures had their **failures read while
designing a fix** (`ml/eval/contamination.py`). A measurement on a sample whose failure shaped the
rule that now passes it is a regression measurement. It tells you the rule still works. It cannot
tell you how the system behaves on language nobody anticipated.

`ml/eval/CONTAMINATION.md` is the authoritative ledger. The rule it states is unchanged here: no
sample of corpus `2026.09.11-1`, and no translation, transliteration or paraphrase of one, may
become independent locked evidence. `ml/eval/corpus/locked.json` stays empty until humans produce
something that qualifies.

## 2. Why Claude cannot author the official corpus

Three independent reasons, any one of which is sufficient.

**Circularity.** The same model that helped write the detectors, the lexicons and the negation
scoping would be writing the test for them. It would produce exactly the negation patterns the
rules already handle and exactly the transliterations already in the lexicon, because those are
the ones it finds salient. The measurement would be of the overlap between two artefacts of the
same process, and it would look excellent.

**Distributional narrowness.** An LLM writing "Hinglish distress" produces a register — a fairly
clean, fairly standard, fairly middle-register transliteration. Real intake text has typos that
change a consonant cluster, regional words for boycott that do not appear in any dictionary the
model saw, abbreviations, and understatement that is culturally specific. The published critical
misses were all of this kind. Generated text does not contain the failure mode it is meant to find.

**Provenance.** Invariant: a human decides. A label on a crisis sample is a safety judgement, and
the repository requires two independent humans for it. An identity in a review record must be a
real recorded human identity. A corpus authored by a model and labelled by a model has no
provenance to audit — and once someone reads a number derived from it, the number is in the deck.

So the tooling is built so that the agent **cannot** contribute content even by accident:

* no module in `ml/eval/blind/` contains a scenario, a label, or a person;
* the submission template is blank and validation refuses every blank field;
* `identity.py` refuses placeholder, bot and AI-shaped names for authors, reviewers and
  adjudicators, and refuses `kind` other than `human`;
* every state transition requires an `--actor` that is already on a human roster;
* the test fixtures are flat sentences about forms and bus stops, held in temporary directories,
  and carry no safety content to label.

## 3. The private evaluation root

The corpus never enters Git. All executable paths resolve from `SAHAY_EVAL_ROOT` (or `--root`);
there is no default, and an unset root exits `2` with a message that names no path.

```text
<SAHAY_EVAL_ROOT>/
  intake/                       blank templates: submission, roster
  author-submissions/<v>/       one JSON per submission (contains narrative)
  assignments/<v>/              roster.json, assignments.json
  blinded-reviews/<v>/packets/  exported blinded packets (contain narrative)
  blinded-reviews/<v>/records/  imported review records
  adjudication/<v>/             adjudication packets and records
  eligible/<v>/                 eligibility reports (ids and reason classes only)
  frozen/<v>/                   corpus.json, labels.json, review_manifest.json,
                                coverage_report.json, freeze_manifest.json
  manifests/<v>/                content-free manifest copy
  reports/<v>/                  status and evaluation output
  rejected/<v>/                 rejected and superseded records, kept forever
  ledgers/<v>/                  submissions / reviews / adjudications / states .jsonl
```

`ledgers/` is an addition to the recommended layout: the four hash chains are the integrity
backbone and belong in one directory a backup job can copy together.

A local example, documentation only: `D:\SAHAY-AI-Datasets\private-evaluation\v1`.

**What may be committed.** Schema definitions, blank templates, the coverage plan, command
documentation, tests using temporary data, and — only after a real freeze — a content-free
manifest in `ml/eval/blind/freeze_manifests/`. Nothing else. No scenario text, no label tied to a
narrative, no reviewer reasoning, no reviewer identity.

### Recovery and backup

The private root is the only copy of work that costs humans days. It is also, by design, outside
version control, so nothing else protects it.

* Back up the whole root daily to separate physical media, and keep the four ledger heads
  (`blind_corpus verify-ledgers`) in a place the backup cannot overwrite — the freeze manifest and
  a written log both qualify. Truncating a ledger, or rewriting it with recomputed hashes, is only
  detectable against an externally recorded head.
* Treat the backup as sensitive: it contains unpublished evaluation text whose value depends on
  nobody having seen it. Restrict access to the corpus owner and the reviewers.
* Before a freeze, verify the ledgers and record the heads. After a freeze, copy
  `frozen/<v>/` to write-once storage; it is the artefact every later claim rests on.
* If the root is lost, the corpus is lost. Submissions cannot be reconstructed from the committed
  repository, and they must not be: that is the point.

## 4. Status workflow

```text
submitted ──┬─> schema_invalid ────────────────> rejected
            ├─> pii_review_required ───────┐
            ├─> contamination_review_required ─┐
            └─> assigned <─────────────────┴───┘
assigned ──> under_review ──┬─> review_complete ──> eligible ──> frozen ──> evaluated
                            └─> conflicted ──> needs_adjudication ──┘            │
                                                                                 v
                                                          contaminated_after_evaluation
```

Every state is in `ml/eval/blind/states.py::STATES`, and `TRANSITIONS` is the whole rule. There is
no transition from `submitted` to `frozen`, and `eligible` is reachable only from
`review_complete`. `rejected` and `contaminated_after_evaluation` are terminal, and nothing is ever
deleted from either.

Every transition records **actor, timestamp, prior state, new state, written reason, input hash,
record hash** and is appended to the state ledger. `input_sha256` is what makes a transition
falsifiable later: a move to `review_complete` names the review comparison it rests on, a move to
`eligible` names the eligibility report, a move to `frozen` names the corpus hash. A transition
into any of those states without an input hash is refused.

## 5. Blinding guarantees

A review packet contains: submission id, language, script, turns, label definitions, permitted
values, evidence instructions, abstention instructions, the ambiguity-flag vocabulary, the
blinding notice, the attestation sentence, and a blank record.

It cannot contain, structurally rather than by promise:

| Withheld | Why it cannot leak |
|---|---|
| Detector output, SVI, band, alerts, pipeline evidence | No module in `blind/` imports anything that can produce them (§7). |
| The author's expected routing | An author submission has **no** label and no expected-outcome field. There is nothing to leak. |
| Author identity, declared slices, lineage | `build_packet` copies a five-key allow-list and drops the rest. A slice name such as `explicit_negation` is the answer written on the envelope. |
| Another reviewer's decision | Packets are built from the submission, never from the review ledger. |
| Baseline failure reports, current pass/fail | Nothing in `blind/` reads `ml/eval/results/`. |

The reviewer re-hashes what they were shown (`narrative_sha256`, computable from the packet alone)
and copies that hash into their record, so a record can be proved to describe exactly the text the
author submitted. A reviewer cannot alter the submission: their record is a separate document in a
separate ledger, and the freeze gate reads the narrative only from the submission ledger.

## 6. Reviewer assignment, conflict and adjudication

Assignment (`blind/assignment.py`) is a pure function of the submissions and the roster: the same
inputs always give the same allocation, so nobody can quietly re-roll one. It refuses to assign a
sample to its own author by `person_id` or by account, gives every sample **two distinct humans**,
enforces language competency, treats one human with two accounts as one human, and spreads load by
a per-submission rotation derived from the submission id.

Criticality is unknown before annotation — that is what blinding means — so every sample gets two
reviews, and the repository's two-reviewer requirement for crisis and immediate-danger labels binds
when such a label actually appears.

**Conflicts.** `compare_reviews` reports disagreement field by field: routing, abstention,
decision, each of the eleven labels, and the evidence turn sets. A *critical* conflict is a
disagreement about `crisis_self_harm`, `immediate_danger` or whether the case is routed Critical —
deliberately not about the band, since Moderate against High is an ordinary priority disagreement.

**Copied reasoning.** Identical reasoning after normalisation is flagged for human inspection. It
is a flag and nothing else: identical text can mean copy-paste, a shared template, a very short
sentence, or two people reaching the same conclusion in the same words. It never proves collusion
and never invalidates a record.

**Adjudication** (`blind/adjudication.py`) is an append-only record that resolves a disagreement.
It cannot edit a review and cannot edit the narrative: the record has no field able to hold
scenario text and unknown fields are refused. The adjudicator may not be the author, may not be one
of the reviewers in conflict, must be marked `can_adjudicate`, and must be competent in the
language. A broken review ledger blocks adjudication outright.

For crisis or immediate-danger disagreements, the conservative (most severe) routing may be
recorded so the case is not under-routed while the question is open — but the sample stays
**ineligible** until two distinct reviewers actually hold the same critical view, normally via a
third independent blind review. `critical_conflict_resolved` is checked against the review records,
never taken on trust, and `resolution_basis: adjudicator_decision` is refused for a critical
disagreement.

> The rule that an adjudicator may not be one of the conflicting reviewers is **stricter** than the
> minimum the staffing policy states. It applies the same independence principle the author rule
> rests on. It is listed in `blind/STAFFING.md` for lead sign-off.

## 7. Leakage and similarity controls

`blind/leakage.py` builds an index of every exposed text — all five corpus files plus every fixture
id named as a published failure or a regression target — and compares a submission with plain
string and set operations. No fuzzy-matching library is used, and none may be added.

**Blocks** (a human cannot clear these; the sample can only be rejected or re-authored from
scratch under a new id):

* exact normalised whole-scenario match;
* stable content-hash match over the normalised victim turns;
* the same turn set in a different order;
* a substantive turn (five tokens or more, not a common phrase) reproduced verbatim;
* declared lineage whose parent is an exposed sample.

Normalisation folds NFKC, case, zero-width characters, Devanagari nukta, chandrabindu, curly quotes,
dashes, all punctuation and all whitespace. A change of punctuation, case, spacing or Unicode
composition alone therefore cannot hide a copy — `ml/tests/test_blind_corpus.py` proves each of
those four separately.

**Warnings** (human adjudication with a recorded reason, not rejection): Jaccard token overlap at
or above 0.70 on texts of at least 8 tokens, and a shared six-token window that exactly one exposed
sample uses.

Common short safety phrases — "I need help", "mujhe madad chahiye", "मुझे मदद चाहिए" — are the words
real callers use. A turn whose whole text is one of those never blocks on its own, and short turns
are excluded from the phrase and overlap rules entirely. What is caught is the reproduction of a
*scenario*.

**Limits, stated rather than hidden.** Cross-script copying by hand (a Devanagari fixture
transliterated to Latin) is not detected by string comparison; it is covered by the author
attestation, the declared-lineage rules and human review. A close paraphrase sharing no six-token
window and little vocabulary will pass — which is why authors must not have read the exposed
corpora. That is a staffing rule, not a software one.

## 8. The prediction firewall

No module in `ml/eval/blind/` imports `ml.assessment`, the detectors, the classifiers, the
recommendation logic, the crisis pre-check, the guardrail validator, the SVI engine, `ml.eval.predict`
or a backend assessment adapter. The list is `blind/firewall.py::FORBIDDEN_MODULES`.

`ml.guardrails` is on the list as a *package*, because importing any submodule of it executes
`ml/guardrails/__init__.py`, which loads the validator and the pre-check. That is why
`blind/normalize.py` exists instead of reusing `ml.guardrails.normalize`; the two fold the same
things and the blind one is pinned by its own tests.

Evidence, not assertion. `ml/tests/test_blind_freeze.py`:

* runs `init`, `validate-submission`, `submit`, `assign`, `export-review`, `status`, `coverage`,
  `verify-ledgers` and `freeze --dry-run` in a clean subprocess and asserts that **no** forbidden
  module is in `sys.modules` afterwards;
* does the same for `blind_evaluation run` refusing without a frozen corpus;
* asserts `assert_clean()` does raise when the pipeline *is* loaded;
* greps every `blind/*.py` import line for the forbidden names.

Both command-line entry points call `firewall.assert_clean()` before dispatching.

## 9. Freeze

`blind_corpus freeze` refuses unless all fourteen conditions hold, and writes **nothing** when it
refuses:

1. the coverage plan is satisfied, per language;
2. every sample still passes schema validation;
3. the required human reviews exist;
4. reviewer roles and language competencies are recorded and adequate;
5. no author reviewed their own sample;
6. crisis and immediate-danger labels rest on two agreeing human reviewers;
7. every conflict is adjudicated and resolved;
8. every PII and contamination flag was cleared by a human, with a reason;
9. no sample, and no declared derivative, appears in an exposed or training corpus;
10. the review ledger verifies end to end;
11. the adjudication ledger verifies end to end;
12. every content hash still matches its submission;
13. no prediction has been produced for this corpus version;
14. this corpus version has not already been frozen.

Outside Git it writes `corpus.json`, `labels.json`, `review_manifest.json`, `coverage_report.json`
and `freeze_manifest.json`. The manifest carries the corpus SHA-256, a per-file SHA-256, the
reviewer-count summary, the language / category / slice totals, the freeze timestamp, the freeze
actor and all four ledger heads.

`freeze --public-manifest PATH` additionally writes the **content-free** subset for Git:
version, counts, totals, hashes, ledger heads, timestamp. No scenario text, no per-narrative label,
no reviewer identity, no reasoning. `ml/eval/blind/freeze_manifests/` holds these, and it is empty
today — writing one now would be a fabrication, and the gate refuses long before it could.

`blind_corpus verify-frozen` re-verifies every file hash, the corpus hash and every ledger head.

## 10. The one-time official evaluation

```powershell
python -m ml.eval.blind_evaluation run --root "$env:SAHAY_EVAL_ROOT" --version "v1" --actor person-001
```

Today this refuses with exit code 12: no corpus has been frozen, so no independent measurement
exists. The measurement path itself **is implemented** — `ml/eval/blind_evaluation.py` plus
`blind/adapter.py` and `blind/results.py` — and is exercised end to end in
`ml/tests/test_blind_evaluation.py` against complete miniature corpora built in temporary
directories. What is missing is the corpus, not the code.

### Precondition sequence

Steps 1-8 run with **no prediction module loaded**. Each refuses before the next is attempted, so a
configuration mistake can never reach the pipeline.

| # | Check | Exit on failure |
|---:|---|---:|
| 1 | resolve the version, strictly beneath `SAHAY_EVAL_ROOT` | 2 |
| 2 | validate configuration: root exists, version shape, `--actor` is a roster human | 2 |
| 3 | a freeze manifest exists for this version | 12 |
| 4 | the manifest's `corpus_version` matches the request, and it is complete | 10 |
| 5 | the corpus SHA-256 and every per-file SHA-256 verify | 10 |
| 6 | the four recorded ledger heads verify | 10 |
| 7 | every frozen sample is in a state this run permits | 14 |
| 8 | the corpus has not already been evaluated (unless `--regression`) | 2 |
| 9 | **lazy import boundary**: `_pipeline()` imports the pipeline | — |
| 10-12 | predictions, metrics, repeat-run determinism | 13 |
| 13 | atomic publication | 13 |
| 14 | exposure record and state transitions | 14 |

A state failure whose entire cause is a completed evaluation is reported as exactly that (exit 2,
"use `--regression`") rather than as a puzzle about states.

### The lazy-import boundary

`_pipeline()` is the only place any prediction module is imported, and it is a function body, not a
module-level import. Importing `ml.eval.blind_evaluation`, parsing arguments, or refusing for any
of the eight reasons above therefore loads nothing that can produce a prediction.
`ml/tests/test_blind_evaluation.py::TestPredictionFirewall` proves this in clean subprocesses for
each refusal individually, asserts that a *successful* run does load `ml.assessment`, and greps the
module's own import lines.

### Reuse, and the adapter

Nothing is re-implemented. The run calls `ml.eval.predict.predict`, the metric tables inside
`ml.eval.evaluate`, `ml.eval.metrics`, `ml.eval.checks.determinism` and `scenario_replay`, and
`ml.eval.redteam.prohibition_coverage` — the same code `run_eval` uses. Predictions are computed
once and shared by every slice cut, so a slice can never disagree with the headline. No threshold,
weight, override or abstention rule is touched, and the command exposes no option that could tune
one: tuning through this path is impossible by construction, and a test asserts the parser has no
such flag.

`blind/adapter.py` is the single explicit place where the frozen private schema becomes an
evaluator sample. Its derivations are listed in the module and copied into every report under
`derived_expectations`:

* **channel** is fixed to `mobile_chat`. The blind corpus is written text, so the acoustic
  dimension D4 is structurally unavailable for every sample and **no acoustic claim can be made
  from these results**.
* **`expected.crisis_precheck`** is a **derived proxy** from the reviewed `crisis_self_harm` label,
  not a separately annotated ground truth. Reviewers are blind to pipeline internals and are never
  asked whether a synchronous pre-check should fire, so pre-check recall is measured against a rule
  the schema already states.
* **`expected.routed_critical`** is the human routing label thresholded at `Critical`. It is the
  routing label, not a band.
* **`expected.band`** is **always null**. See "Routing label, SVI band and abstention" below.
* **`tags`** is empty: the schema tag vocabulary is not the blind challenge-slice vocabulary.
* ids stay in the `SUB-` namespace so a blind sample can never be mistaken for a `DEV-`, `CAND-` or
  `LOCK-` fixture.

### Routing label, SVI band and abstention

These are three different things that share one vocabulary, and an earlier version of this adapter
conflated the first two. They are now kept apart by construction.

| | What it is | Who produces it |
|---|---|---|
| **routing label** | what should HAPPEN — who is woken up and how fast | two blind human reviewers |
| **SVI band** | what the deterministic scorer OUTPUTS | the pipeline |
| **Needs Human Assessment** | no score was produced at all | the pipeline's abstention |

`Low | Moderate | High | Critical` is the vocabulary of both the routing label and the band, and
that is the whole of their relationship. The blind annotation schema asks reviewers for a routing
label and **never** for a band, so:

* the report compares predicted routing **only** against the human routing label, thresholded at
  `Critical` — the only routing decision the pipeline actually makes, since it emits no four-level
  routing;
* the band distribution is reported **descriptively**, with no accuracy attached;
* **no band-accuracy metric is computed at all**, and `band_ground_truth.available` is `false` in
  every report with the reason spelled out;
* a routing label is never converted into a band. `expected.band` is `null` for every blind sample —
  which is how `ml/eval/evaluate.py` already represents unspecified ground truth, so nothing is
  fabricated to satisfy the older API — and `adapter.validate_adapted` refuses any sample whose band
  was filled in from the routing label;
* **Needs Human Assessment is counted separately from the scored bands.** It is an abstention, not a
  verdict, and folding it in with `Low` would turn "we declined to score this" into "we scored it
  low".

If a future annotation round asks humans to label an SVI band independently, that becomes a real
ground truth and a band-accuracy metric may then be added. Until then there is nothing to measure
against, and the report says so rather than inventing a number.

### Report schema

One JSON result plus a narrative-free Markdown companion. Top level: `result_version`, `run_id`,
`run_at`, `run_by`, `independence`, `corpus` (version, plan version, corpus SHA-256, freeze-manifest
SHA-256, per-file hashes, sample count, freeze timestamp), `ledger_heads`, `versions` (pipeline,
scoring, lexicon, validator, adapter), `derived_expectations`, `sections`, `result_sha256`.

The fourteen sections, fixed in `blind/results.py::REQUIRED_SECTIONS`:

| Section | Contents |
|---|---|
| `detector_metrics` | precision, recall, F1, specificity and **explicit denominators** per detector; undefined metrics are `null`, never 0.0; `explicit_human_request` is excluded with its reason |
| `by_language` | en, hi and hinglish, each with its own detector table and routing block |
| `by_category` | all twelve coverage-plan categories |
| `by_challenge_slice` | all twenty-two declared slices, including negation, quotation, attribution, misspelling and the adversarial ones |
| `label_slices` | the label-derived negation, quotation/attribution and adversarial cuts |
| `critical_misses` | count, sample ids, per-sample detail, critical-event miss rate, crisis pre-check table |
| `false_escalations` | count, sample ids, per-sample detail |
| `abstention` | expected, achieved, coverage, unexpected abstentions, needs-human count |
| `evidence_link_validity` | cited-id validity, positives with valid evidence, overlap and **exact agreement** against labelled evidence |
| `routing_labels` | the human routing-label distribution, how many the pipeline routed Critical, and the critical-routing table |
| `svi_distribution` | scored-band distribution (descriptive), Needs Human Assessment counted separately, the D4 structural check, per-sample SVI, and an explicit `band_ground_truth: available=false` |
| `determinism` | two full prediction passes, identical or not, plus the hash and the excluded metadata |
| `scenario_replay` | incremental replay consistency for every multi-turn sample |
| `guardrail_prohibition_coverage` | the validator's prohibition coverage, with a note on applicability |

Reports name samples and turns by id. No scenario text appears in a report, a log line or an error
message, and a test asserts it for both the JSON and the Markdown.

### Independence, publication and exposure

**Publication has one definition: the result JSON existing at its final path.** Not the Markdown,
not a console line, not a temporary file. Everything else hangs off that.

The first successful run on a frozen corpus is labelled `independent_evaluation` and written to
`reports/<version>/evaluation-independent.json`. Publishing it exposes the corpus: an exposure
record is written to `frozen/exposure.json` and every sample moves `frozen -> evaluated ->
contaminated_after_evaluation`. Those transitions are tied to publication and happen immediately
after it.

Every later run requires `--regression`, is labelled `regression_after_exposure`, is written to its
own uniquely named file under `reports/<version>/regression/`, and is compared field by field
against the independent result; the comparison travels in the report as `compared_to`. The
independent result is never overwritten — `finalize` refuses outright if it already exists, even if
somebody deletes the exposure record. A failed or interrupted run changes no state at all.

Determinism and regression comparisons exclude exactly five documented non-substantive fields —
`run_id`, `run_at`, `run_by`, `independence` and `compared_to` (plus the hash computed over the
rest). Every other field, including every metric, must match exactly.

### Atomic finalization and recovery

1. write every artefact into `reports/<version>/.tmp-<run_id>/`;
2. validate the completed result — all fourteen sections present and populated, determinism true;
3. compute `result_sha256` over the substantive content;
4. re-read what was written and re-validate it;
5. `os.replace` into the final paths, **the JSON last**.

`os.replace` is atomic per file; a multi-file set is not atomic as a group, and the ordering is
chosen so that every incomplete state is harmless and detectable:

| Interrupted at | State | Recovery |
|---|---|---|
| before any rename | nothing published, nothing exposed | the next run deletes the temp directory and starts again |
| after the `.md`, before the JSON | still nothing published | `status` lists it under `pending_temporary_artefacts`; the next run replaces the companion |
| after the JSON, before the exposure record | **published and exposed**, but the ledger does not say so | `unrecorded_publication` detects it and `repair()` appends the exposure record and the state transitions from the published result. The pipeline is never re-run and the result is never recomputed. |

`repair()` runs automatically at the start of every `run`, is idempotent, and skips a sample already
in its final state, so it cannot corrupt the state ledger.
`python -m ml.eval.blind_evaluation clean-temp` removes temporary directories and never touches a
finalized result.

### Result storage paths

```text
<root>/reports/<version>/evaluation-independent.json     the one independent result, immutable
<root>/reports/<version>/evaluation-independent.md       its narrative-free companion
<root>/reports/<version>/regression/evaluation-regression-<run_id>.json
<root>/reports/<version>/regression/evaluation-regression-<run_id>.md
<root>/reports/<version>/.tmp-<run_id>/                  work in progress only
<root>/frozen/<version>/exposure.json                    written at publication
```

All outside Git. The freeze manifest is never mutated by an evaluation, so a frozen corpus keeps
verifying against its original hashes for ever.

**How evaluation makes a corpus exposed.** The first run is the only independent measurement that
corpus can ever produce. Reading its outcomes — and above all changing a rule because of them —
turns every sample into a regression fixture, exactly as happened to `candidates.json` on
2026-09-11. Reporting a later run as independent evaluation is a documentation error, not a matter
of judgement, and the tooling refuses to produce that label a second time.

**A future v2 holdout.** Another independent number needs another corpus. Create it as a separate
corpus version (`--version v2-holdout`) with its own coverage plan, its own private directories and
its own ledgers; the layout is versioned throughout. Rules that carry over: it must be authored by
people who have not seen the v1 results (v1 authors may write for v2 only if they were not shown
the outcomes); no sample may be derived from a v1 sample, and the leakage index for v2 must include
the frozen v1 corpus; and it must stay unfrozen and unevaluated until there is a specific question
worth spending it on. A holdout spent early is a holdout wasted.

## 11. Commands and exit codes

```powershell
python -m ml.eval.blind_corpus init                 --root R --version v1
python -m ml.eval.blind_corpus validate-submission  FILE
python -m ml.eval.blind_corpus submit               FILE --actor person-001
python -m ml.eval.blind_corpus roster-status
python -m ml.eval.blind_corpus assign               --actor person-001
python -m ml.eval.blind_corpus export-review        --actor person-001
python -m ml.eval.blind_corpus import-review        FILE --actor person-001
python -m ml.eval.blind_corpus export-adjudication  SUBMISSION_ID
python -m ml.eval.blind_corpus adjudicate           FILE --actor person-001
python -m ml.eval.blind_corpus status
python -m ml.eval.blind_corpus coverage
python -m ml.eval.blind_corpus --json status        # --json and --root precede the subcommand
python -m ml.eval.blind_corpus verify-ledgers       [--expect-head reviews=COUNT:SHA256]
python -m ml.eval.blind_corpus freeze               --actor person-001 [--dry-run] [--public-manifest PATH]
python -m ml.eval.blind_corpus verify-frozen
python -m ml.eval.blind_corpus exit-codes
python -m ml.eval.blind_evaluation run              --root R --version v1 --actor person-001
python -m ml.eval.blind_evaluation run              --regression --actor person-001
python -m ml.eval.blind_evaluation status
python -m ml.eval.blind_evaluation clean-temp
```

Every command works only inside the configured root, refuses a path outside it, prints no scenario
text in either output mode, invents no human input, and never writes to `ml/eval/corpus/`.

| Code | Meaning |
|---:|---|
| 0 | success |
| 1 | internal error |
| 2 | invalid command or configuration (root unset, unknown actor, duplicate submission) |
| 3 | schema validation failure (submission, review, adjudication, roster, binding, hash) |
| 4 | privacy: possible personal information, human inspection required |
| 5 | contamination or similarity review required |
| 6 | missing required human review (including an assignment shortfall) |
| 7 | reviewer conflict |
| 8 | adjudication required or invalid |
| 9 | coverage plan incomplete |
| 10 | ledger or hash verification failure |
| 11 | freeze refused |
| 12 | no frozen corpus |
| 13 | evaluation failure |
| 14 | invalid status transition |
| 15 | prediction module loaded before freeze |

## 12. Coverage plan

`ml/eval/blind/coverage_plan_v1.json` is the versioned target: **180 samples, 60 en / 60 hi /
60 hinglish**, with a minimum and a written reason for each of 12 categories and 22 challenge
slices. Counts are minimums and a sample may satisfy several at once, so the sums exceed 180 by
design. Language totals are hard: a shortfall in one language blocks the freeze rather than being
absorbed by the other two. Difficulty must come from linguistic structure, never from demographic
stereotype; a sample whose only difficulty is a demographic marker must be rejected in review.

Category membership is taken from the frozen human labels. Slice membership is author-declared and
stops counting if a reviewer raises `slice_declaration_looks_wrong`. Changing a minimum bumps
`plan_version` and needs the same lead approval as a contract change.

See `blind/AUTHOR_INSTRUCTIONS.md` for what each slice means in practice.

## 13. Limitations

* **PII detection is a screen, not a guarantee.** It finds shapes: digit strings, e-mail and URL
  shapes, handles, identifier keywords, self-introduction phrasing, date-of-incident formats. It
  cannot recognise an ordinary personal name, a real village, the real date of a real incident, or
  a narrative a survivor would recognise as their own. A human must read every submission.
* **Similarity detection is deterministic and literal.** It cannot see a hand-made cross-script
  transliteration or a skilful paraphrase. Warnings need human adjudication; blocks are certain but
  not complete.
* **The hash chains prove self-consistency and order, not authorship.** They are not signed.
  Tail truncation and whole-file rewrites are detectable only against an externally recorded head.
  Authorship rests on the named human identity and the attestation that identity signed.
* **Identity checks refuse placeholders, not determined humans.** A person can type a plausible
  name. What is guaranteed is that nothing in this repository can fill a record with
  `TODO-reviewer-1`, an agent name or a bot account.
* **Attestations are declarations.** "No language model wrote this" cannot be verified by software.
  It is recorded, hashed and attributable, which is what makes it worth signing.
* **Slice labels are unverified metadata.** They are accounting for coverage, never evidence.
* **The measurement path is implemented and tested, but never yet run on a real corpus.** It is
  exercised only against miniature temporary corpora in tests. The first real run will be the first
  time the adapter meets human-written text at scale.
* **No acoustic claim can come from this corpus.** Every sample is written text, so the channel is
  fixed to `mobile_chat` and D4 is structurally unavailable throughout.
* **`expected.crisis_precheck` is a derived proxy, not annotated.** Pre-check recall is therefore a
  measurement against a rule the schema already states, not against an independent human judgement.
* **There is no band ground truth.** The annotation schema asks for a routing label, never an SVI
  band, so the band distribution is descriptive and no band accuracy exists to report. Adding one
  would require a new, independently reviewed band label.
* **Multi-file publication is not atomic as a group.** Each rename is atomic; the ordering makes
  every interrupted state harmless or repairable, and one window (published result, missing
  exposure record) is repaired rather than retried.
* **180 samples is small.** Per-language, per-slice cells will have single-digit support. Report
  counts alongside every rate, and do not claim a difference the support cannot carry.

## 14. What is still required from humans

See `blind/STAFFING.md` for the full staffing analysis. In short: at least 3 authors and 4
reviewers (of whom at least 2 read Hindi and at least 2 are competent in code-switching) plus 1
adjudicator who authored nothing, no one person doing more than one role on any single sample, and
roughly 180 scenarios written plus 360 blind annotations recorded before a freeze is even possible.

Until that work is done: locked count remains 0, official metrics remain unavailable, and every
number in `ml/eval/results/` is regression performance.
