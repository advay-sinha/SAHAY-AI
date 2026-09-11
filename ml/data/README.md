# ml/data — external dataset governance

This directory governs external datasets. It is **metadata only**:

- no raw data, extracted files, audio or model files ever enter Git;
- nothing here is used by the deterministic pipeline or its evaluation;
- nothing here tunes any rule.

| Path | Purpose |
|---|---|
| `registry/datasets.json` | The registry: one record per dataset (42 fields; schema 1.1.0 adds `sensitivity_flags`), with no machine paths |
| `registry/schema.json` | Documentation form of the schema. The executable validator is `governance.py`. |
| `governance.py` | Registry validation, dataset-root confinement, use guards |
| `archive_safety.py` | Untrusted-ZIP checks and bounded extraction |
| `audit_external.py` | Audit command: integrity, archive safety and governance gaps |
| `inventory.py` | Non-extracting inventory of the whole dataset root (sizes, hashes, ZIP findings, CSV column names) |
| `external_corpus.py` | Governed adapter from an external dataset to a private normalised development format |
| `label_firewall.py` | Refuses every automatic mapping from a source label to a SAHAY label, band, SVI or D4 |
| `external_report.py` | Private exploratory research composition report and retention recommendation; never runs or tunes the pipeline |
| `external_analysis.py` | `external_exploratory_analysis`: exploratory firing rates on stratified samples |
| `cards/*.md` | Dataset cards |
| `proposals/d4-acoustic-distress-evaluation.md` | Future D4 experiment (proposal only) |

## 1. External directory layout and `SAHAY_DATASETS_ROOT`

Datasets live **outside the repository** under a root named by the environment variable `SAHAY_DATASETS_ROOT`. No executable code has a default path. If the variable is unset, the audit stops with a clear message (exit code 4). Layout, with the Windows machine used in 2026-09 as an example only:

```text
<SAHAY_DATASETS_ROOT>                 e.g. D:\SAHAY-AI-Datasets   (documentation example)
  corpus/text/english/<dataset>/<archive>
  corpus/text/hindi/<dataset>/<archive>
  corpus/text/hinglish/<dataset>/<archive>
  corpus/audio/english/<dataset>/<archive>
  corpus/audio/hindi/<dataset>/<archive>
  corpus/audio/multilingual-indic/<dataset>/<archive>
  extracted/<dataset>/<sha256[:12]>/     created only by an approved extraction
```

The registry's `modality` and `primary_language` fields cover these combinations. Languages are `en`, `hi` (Hindi, Devanagari), `hi-Latn` (romanised Hindi or Hinglish) and `mul-IN` (multilingual Indian); modalities are text, audio, audio+text and multimodal.

## 2. Why raw datasets are excluded from Git

- Licences rarely permit redistribution.
- Real narratives carry privacy risk.
- Archives are large.
- A committed copy can't be withdrawn.

Tests enforce this (`ml/tests/test_dataset_governance.py`): no tracked archive, audio or model file, and no dataset path in application modules.

## 3. Registering a dataset (no application code changes)

1. Before downloading, get an approved EXT decision in `docs/EXTERNAL_DECISIONS.md` (owned by the leads, not ML).
2. Add a record to `registry/datasets.json`:
   - `download_status: not_downloaded`, `review_status: metadata_pending`;
   - licence and provenance fields filled from authoritative sources, with URLs and the access date;
   - `unknown` where something can't be verified. Never guess.
3. After the download, place the file under the layout above. Record `byte_size` and `sha256`, and set `local_relative_path` (relative, forward slashes).
4. Run the audit (section 4) and add a dataset card in `cards/`.
5. A human reviews the licence (section 5) and changes `review_status` in a reviewed commit. Tools never change it.

## 4. Archive audit

```powershell
$env:SAHAY_DATASETS_ROOT = "D:\SAHAY-AI-Datasets"      # example
python -m ml.data.audit_external                        # or: --root <path>
```

The audit does the following:
- resolves each file strictly beneath the root, refusing traversal;
- verifies the size and SHA-256;
- reads only the ZIP central directory;
- rejects members with absolute or traversal paths, drive letters or alternate data streams, device names, duplicate names, the encryption flag, or the symlink attribute, plus member names with an archive-looking or executable-looking extension;
- rejects a declared expansion above the ceiling (2 GiB), a member compression ratio above 100, or an overall ratio above 50;
- treats a registered file as "not an archive" only when it is not a ZIP **and** its record says `archive_safety_status: not_applicable` (a loose, already-extracted file). A ZIP is always inspected, whatever its name or registry entry, so a ZIP renamed to `.csv` cannot skip the checks;
- writes `runtime/dataset-audit/audit.{json,md}` (ignored by Git), containing counts and extensions only: no member names, no content, no absolute path.

**Scope limit.** The audit reads the ZIP central directory only, never member bytes. A pass means that no member has an unsafe name or attribute, and that no member *name* looks executable or like a nested archive. It does **not** prove that the file contents are non-executable, benign or free of personal data.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | all verified and approved |
| 2 | integrity mismatch, missing file or unsafe archive |
| 3 | governance approval missing |
| 4 | configuration error |

## 5. Licence review

- Use only official publisher, repository, paper or dataset-host pages. Record the exact URLs and access dates in `evidence_urls` and `date_checked`.
- A paper's licence (for example the ACL Anthology CC BY 4.0 notice) is **not** the dataset's licence.
- A download link is **not** permission.
- If the terms can't be verified, the dataset stays `licence_pending` or `quarantined` and is neither extracted nor used.

## 6. Extraction

```powershell
python -m ml.data.audit_external --extract <dataset_id>
```

Extraction is refused unless all of these hold:
- the registry state permits research use;
- the size and SHA-256 match;
- every archive check passes;
- the destination `extracted/<id>/<sha[:12]>` is beneath the root, outside the Git worktree, and empty.

Members are written one by one with the total capped at the ceiling. Nothing is executed and no audio is opened.

Extraction is **all-or-nothing**. Members are written into a temporary sibling directory, and that directory is moved into place only after the last member succeeds. If anything fails part-way — a member escapes, the ceiling is crossed mid-stream because the archive under-declared its sizes, a member would overwrite a file — the temporary directory is removed and the destination is left as it was.

## 7. Review states

`unregistered → metadata_pending → licence_pending → integrity_verified → approved_for_research → approved_for_evaluation → approved_for_training`, with `quarantined` and `rejected` reachable from any state.

- Selecting a dataset for a purpose (`governance.select_for`) requires the matching approved state.
- A downloaded file is never approved automatically.
- While any licence field (`licence_name`, `licence_url`, `redistribution`, `commercial_use`) is `unknown`, the only valid states are `unregistered`, `metadata_pending`, `licence_pending`, `quarantined` and `rejected`.
- `official_locked_test_allowed` is false for every external dataset by default.
- A dataset populates an SVI dimension only with an approved mapping study. D4 has none.

## 8. Why external data is not used by the deterministic evaluation

Every registered dataset is `licence_pending` or `metadata_pending`, and none has an approved EXT decision. The deterministic evaluation (`ml/eval`) reads only the fictional corpora in `ml/eval/corpus/`, and a test proves it opens no external dataset.

External data is also **not holdout** just because the pipeline hasn't read it yet (`ml/eval/CONTAMINATION.md`).

## 9. Locked-fixture review and contamination

- The candidate-review workflow is `python -m ml.eval.review_workflow {export,validate,import,status,validate-ledger}`.
- The review ledger is an append-only SHA-256 hash chain. Editing, deleting, reordering or inserting existing entries is detected on every read. Removing trailing entries, or rewriting the whole chain, is detected only against a recorded head (`status` prints `<count>:<hash>`; check it with `validate-ledger --expect-head`). The chain is not signed.
- The contamination rules are in `ml/eval/CONTAMINATION.md` and `ml/eval/contamination.py`: sample classes, lineage for derived and translated samples, and split rules.

## 10. External corpus intake (private exploratory research only)

External datasets are **never** an independent or locked safety benchmark, and their source labels never become SAHAY labels.

### 10.1 Inventory (no extraction, no content)

```powershell
python -m ml.data.inventory --exclude-pattern <regex>   # repeatable; root from SAHAY_DATASETS_ROOT
```

The inventory walks the root recursively and records, for each file, its relative path, size, extension and SHA-256. It also records:
- ZIP central-directory findings, using the same checks as the audit;
- CSV column names, read from the header line only. They are **withheld** if the first line does not look like column names, because that line might be a data row;
- whether a tiny file is a Git LFS pointer stub (a boolean, nothing printed).

`--exclude-pattern` removes out-of-scope paths before they are opened, hashed or listed, and they are not counted. Output goes to `<SAHAY_DATASETS_ROOT>/reports/inventory/`, never into a SAHAY checkout. It is labelled `<SAHAY_DATASETS_ROOT>`, never a machine path, and the tool-owned `reports/` and `normalized/` directories are never inventoried.

### 10.2 Adapter

```powershell
python -m ml.data.external_corpus specs
python -m ml.data.external_corpus convert --dataset <id>
python -m ml.data.external_corpus convert --dataset <id> --local-research-override `
    --acknowledge "<the exact OVERRIDE_ACKNOWLEDGEMENT sentence>" --operator "<who authorised it>"
```

**By default `convert` is fail-closed.** It runs only when all of these hold, and otherwise refuses before reading any row:
- `governance.select_for(..., "research")` permits it;
- the size and SHA-256 match;
- the spec is valid;
- the spec's source-label ontology is marked verified.

No external dataset is approved, so the default path refuses every one of them.

**The local exploratory research override.** The project owner may authorise private, local, offline exploratory research on a `licence_pending` dataset. This is **research only**. It can never supply data to the MVP, the product, the demo or any victim-facing flow. Invariant 8 is unchanged: real or potentially real victim narratives are never used in the MVP.
- **One gate only.** The override bypasses exactly one gate: the licence-based read gate. On every path, override or not, these stay enforced:
  - private-root confinement;
  - privacy screening;
  - product, MVP and demo exclusion;
  - training and tuning exclusion;
  - redistribution exclusion;
  - locked, blind and official-evaluation exclusion;
  - external-upload exclusion.
- **Per run only.** The override is never stored in the registry and changes no registry field.
- **Both parts required.** It needs `--local-research-override` **and** the exact acknowledgement sentence (`external_corpus.OVERRIDE_ACKNOWLEDGEMENT`). The sentence states that:
  - licensing and privacy approval remain unresolved;
  - processing is local and offline;
  - the data cannot enter the product or demo;
  - the data cannot be used for training, tuning, official evaluation or publication;
  - the operator takes responsibility for access to the private source files.
- **Narrow eligibility.** It lifts only `licence_pending`. Quarantined, rejected and not-downloaded datasets stay refused.
- **Two purposes only:** `local_research_conversion` and `local_research_exploratory_analysis`. It refuses every purpose in `OVERRIDE_REFUSED_PURPOSES`, whatever the acknowledgement says: the product, MVP, demo, victim-facing output, backend ingestion, the locked corpus, blind-corpus intake, corpus freezing, independent or official evaluation, training, threshold, lexicon and model tuning, model publication, publication, redistribution, commercial use and upload.
- **Out of reach entirely:** the blind corpus, freeze and evaluation commands have no override parameter.
- **Walled off from the product:** no backend, frontend, mobile or product module may import this adapter or read its outputs, and a test enforces it.
- **Visible and logged.** It prints a warning that licensing and privacy approval are unresolved, and appends every use to `<SAHAY_DATASETS_ROOT>/reports/overrides/override-log.jsonl`.
- **Traceable output.** Records produced under it carry `governance_basis: local_research_override`, and their manifest records that neither licence nor privacy is approved.

The override does not establish that any licence is valid.

**Quarantine and retention.** Every normalised record and manifest is marked `quarantined_research_artifact`, whatever the governance basis. The rule-based redactor removes URL, e-mail, handle, phone and long-number shapes, but it **cannot detect personal names, places or contextual identifiers**, so the normalised text may still contain them.
- Retain it only while the analysis is actively required.
- Delete the normalised sensitive text once aggregate review is complete.

`external_report` writes a private retention recommendation to `<SAHAY_DATASETS_ROOT>/reports/retention/retention-recommendation.json`. It lists each output by relative path and size. Nothing is deleted automatically, and neither that record nor any machine path is ever committed.

**Documented local copies.** If the registered file is absent, a spec may pin a local copy by relative path, size and SHA-256. The copy is accepted only if that SHA-256 also appears in the reviewed registry record, so no unregistered bytes are ever processed. Dreaddit and EmoInHindi use this: their registered archives are absent, and their loose copies are documented in the records.

Output goes to `<SAHAY_DATASETS_ROOT>/normalized/<id>/<source sha[:12]>/records.jsonl` plus `manifest.json`. Writing is refused inside any SAHAY checkout.

Conversion **streams**: rows are read, normalised, de-duplicated and written one at a time, and only duplicate keys are held in memory. Output is written to a `.partial` file and moved into place, with the manifest last, only on success; a failure leaves no output. Conversion is deterministic, with the first occurrence in source order winning. A rerun with identical input and manifest reports `unchanged`.

The manifest records:
- source rows read;
- units discovered (rows, or dialogues for EmoInHindi);
- records written;
- exclusions by reason;
- the normalised output's SHA-256;
- the governance basis;
- whether the registered file or a documented local copy was read.

Each normalised record carries:
- an opaque id `EXT:<dataset>:<split>:<16 hex>`;
- the dataset id and version;
- the **publisher's** split (`train`, `validation`, `test` or `unsplit`). A source test split is never a SAHAY holdout;
- a SHA-256 source-row identity;
- the language, source-declared or from a row column and never guessed, plus the script counted from characters;
- the raw source label, the namespaced category `source:<dataset>:<value>` and the source-label family;
- the privacy-redacted text, or ordered dialogue turns;
- its derivation history;
- privacy findings by **rule name and count only**. URLs, e-mails, Reddit users and communities, social handles, phone numbers and long numbers are replaced with tokens;
- exact and near duplicate keys;
- contamination status against every exposed SAHAY corpus and published regression target;
- the governance basis and permitted purposes;
- `independently_authored: false` and `locked_corpus_eligible: false`, each with a statement;
- `sahay_mapping.applied: false`;
- `d4.available: false`.

A record has **no** SVI, band or dimension field.

Rows are excluded, never raised, with a reason class: `blank_row`, `column_count_mismatch`, `csv_parse_error`, `encoding_error`, `invalid_json`, `json_not_an_object`, `missing_source_label`, `empty_text`, `text_not_a_string`, `unsupported_source_label`, `unsupported_split`, `invalid_turn_number`, `missing_dialogue_id` or `duplicate_turn_number`. No message, log line or exception quotes record text.

Nothing is translated, generated or paraphrased.

### 10.3 Source-label firewall

`label_firewall.map_to_sahay` refuses every route from a source label to a SAHAY target. These pairs are refused whatever evidence is offered:

| Source | Refused as |
|---|---|
| stress | crisis / self-harm |
| depression label | a psychiatric diagnosis |
| suicide-related label | immediate-danger ground truth, crisis ground truth or a routing decision |
| negative sentiment | vulnerability (SVI or band) |
| emotion intensity | the SVI or a band |
| text emotion | acoustic distress (D4) |
| hate speech | continuing threat without contextual human review |
| neutral, positive or unspecified sentiment, `non-suicide`, not-hate | safe or no-alert ground truth |

D4, the SVI, bands and diagnosis are never populated from any source label. Any other mapping needs a separate human mapping record: a named reviewer, written reasoning, provenance and an attestation.

Even a well-formed record is refused today, because `AUTHORISED_MAPPINGS` is empty. An approval is a lead decision, recorded with an approved study id in the registry's `sahay_dimension_mappings`.

### 10.4 Composition report

```powershell
python -m ml.data.external_report          # without a dataset root it prints the registry-only view
```

The report covers:
- governance state per dataset;
- whether the registry permits conversion, and whether the local exploratory research override could;
- each record's sensitivity flags;
- composition of any converted records: languages, scripts, source splits and labels, duplicates, privacy counts, overlap with exposed SAHAY corpora, exclusions, and the records needing human mapping;
- cross-dataset overlap.

It streams the private records, never reads a raw file, and never runs or tunes the pipeline. Output goes to `<SAHAY_DATASETS_ROOT>/reports/external-report/`.

### 10.5 Exploratory analysis (`external_exploratory_analysis`)

```powershell
python -m ml.data.external_analysis run --local-research-override --acknowledge "<sentence>" [--dataset <id>] [--cap 1000]
```

The run draws a deterministic stratified sample from each converted dataset:
- strata are the source split and the source label (a dialogue uses its most frequent label);
- within each stratum, the cap records (default 1,000) with the smallest `sha256(seed|record_id)` are kept;
- duplicates and copies of exposed SAHAY fixtures are left out;
- splits are reported separately and never pooled.

It then runs the current deterministic pipeline (`ml.eval.predict`, imported lazily after every dataset is authorised) and reports **firing rates only**:
- detector firing rates and the crisis pre-check rate;
- routed-Critical, abstention and Needs Human Assessment rates;
- scored bands where a score exists, and alerts;
- the D4-unavailable rate and evidence-link validity;
- throughput;

all sliced by dataset, split, source label, language and script.

External source labels are not SAHAY labels, so **no precision, recall, F1 or accuracy is computed**. A source label only conditions a rate: "the crisis pre-check fired on X% of rows labelled suicide". The run tunes nothing and exposes no tuning option.

The output is labelled exactly `external_exploratory_analysis`: **exploratory firing rates only**, private research, never product, demo, training, tuning or evaluation evidence. It is written to `<SAHAY_DATASETS_ROOT>/reports/external-analysis/`. `assert_wording` refuses reports that describe external data as *official*, *independent*, *validated*, *clinical accuracy*, *production accuracy* or *locked-set performance*, and `check_report` refuses any accuracy-style metric key.

### 10.6 Registry sensitivity flags

Schema 1.1.0 adds `sensitivity_flags` to every record: `real_user_generated_text`, `potential_victim_narratives`, `minors_possible` and `personal_names_not_reliably_redacted`. The flags tighten handling and never loosen it. A record flagged `potential_victim_narratives` must prohibit `victim_facing_output`, and the validator enforces it. Dreaddit and Suicide Detection carry all four flags; the two Kaggle Hinglish files carry three; EmoInHindi (simulated per its paper, not verified) carries the name-redaction flag.

### 10.7 What the 2026-09 local root actually held

Portable summary; the machine path is not recorded:

- **No ZIP archives.** Every dataset was a loose, already-extracted file, unpacked outside the governed extraction mechanism.
- **The registered Dreaddit and EmoInHindi archives are absent from that root.** What is present are documented local copies:
  - a third-party Kaggle re-upload of Dreaddit: 715 rows, the size of the paper's test split;
  - the extracted EmoInHindi CSV: 44,247 utterances in 1,814 dialogues, with lower-case labels, `user`/`bot` roles, and one label (`confused`) that the paper does not list.

  Both are noted in the existing records, not duplicated.
- **CREMA-D was a Git clone without its Git LFS objects.** All 22,326 media files are 130–132-byte pointer stubs, so no audio or video is present and no acoustic processing is possible. The repository README states an ODbL/DbCL licence, but the registry leaves every licence field `unknown` until a human licence review confirms it.
- **Three new text datasets are registered at `licence_pending`:**
  - `reddit_suicide_detection`;
  - `hinglish_hate_speech_local_derivative`. Its labelled rows are the upstream aggregate's **English** part; 3,201 unlabelled rows from a merged second table are excluded;
  - `hinglish_sentiment_kaggle`, identified from a header-less CSV whose first row matches the Kaggle metadata by hash.
- **Under the owner-authorised local exploratory research override, all five text datasets were converted locally as quarantined research artefacts.** An `external_exploratory_analysis` run (exploratory firing rates only) was made on stratified samples. Outputs and numbers stay beneath `<SAHAY_DATASETS_ROOT>/reports/` and are never committed.

## 11. Reproducibility

```powershell
python -m unittest discover -s ml/tests -t .     # needs no SAHAY_DATASETS_ROOT
python -m ml.data.audit_external                 # optional, local only
python -m ml.eval.review_workflow status
```
