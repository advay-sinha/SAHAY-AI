# ml/data — external dataset governance

This directory governs external datasets. It is **metadata only**:

- no raw data, extracted files, audio or model files ever enter Git;
- nothing here is used by the deterministic pipeline or its evaluation;
- nothing here tunes any rule.

| Path | Purpose |
|---|---|
| `registry/datasets.json` | The registry: one record per dataset (41 fields), with no machine paths |
| `registry/schema.json` | Documentation form of the schema. The executable validator is `governance.py`. |
| `governance.py` | Registry validation, dataset-root confinement, use guards |
| `archive_safety.py` | Untrusted-ZIP checks and bounded extraction |
| `audit_external.py` | Audit command: integrity, archive safety and governance gaps |
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

## 10. Reproducibility

```powershell
python -m unittest discover -s ml/tests -t .     # needs no SAHAY_DATASETS_ROOT
python -m ml.data.audit_external                 # optional, local only
python -m ml.eval.review_workflow status
```
