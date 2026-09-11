# data-scripts/

Manifests, registries, labelling tools and aggregate evaluation results.

Raw audio, processed audio, model weights and datasets live under the external
`DATA_ROOT`, never in Git. Only manifests, checksums, licences, attribution and
anonymised labels are committed.

## Files

> **External datasets** are governed by `ml/data/`:
> - the registry is `ml/data/registry/datasets.json`;
> - the audit is `python -m ml.data.audit_external`;
> - cards are in `ml/data/cards/`.
>
> `dataset_registry.yaml` below is the earlier planning list, kept for history; the JSON registry supersedes it for datasets that exist locally. Its licence entries are unverified.

- `dataset_registry.yaml` — every dataset considered, with status, licence,
  scope, checksum and limitations. `status: proposed` is not approval; approval
  lives in `docs/EXTERNAL_DECISIONS.md`.
- `corpus_manifest.csv` — one row per turn of the locally authored scenario
  corpus. Header only until the scripts are written and reviewed.

## corpus_manifest.csv columns

| Column | Meaning |
|---|---|
| `session_id` | One complete fictional session |
| `scenario_id` | One of the ten scenarios |
| `speaker_id` | Speaker, for speaker-disjoint splits |
| `language` | `hi`, `en` or `hinglish` |
| `condition` | `clean` or `noisy` |
| `turn_index` | Turn order within the session |
| `speaker` | `victim` or `assistant` |
| `text` | Transcript. Fictional; never a real account |
| `audio_path` | Path under `DATA_ROOT`. Never a path inside the repository |
| `crisis` `threat` `medical` `coercion` | High-consequence labels |
| `expected_state` | Dialogue state the machine should reach |
| `expected_band` | Band the assessment should reach, or `needs_human` |
| `split` | `train`, `dev` or `locked_test` |

## Rules

- The ten scenarios cover: immediate danger, crisis, ongoing threat, medical
  urgency, boycott/displacement, coercion, legal status, low-risk request,
  negated or quoted crisis language, and an explicit request for a human.
- High-consequence labels (`crisis`, `threat`, `medical`, `coercion`) require
  two annotators and recorded adjudication.
- The `locked_test` split is fixed before evaluation and never trained on.
- Split by speaker, not by clip.
- Never use real victim or NHAA data.
