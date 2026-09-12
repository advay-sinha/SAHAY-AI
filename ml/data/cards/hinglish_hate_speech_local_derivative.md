# Dataset card — local derivative of a Hinglish hate-speech aggregate

Registry id `hinglish_hate_speech_local_derivative`. **Status: `licence_pending`. No use is approved. Provenance of the local file is unverified.** Checked on 2026-09-11 from public Kaggle metadata, the local header line, and a label-value census taken under the owner-authorised local exploratory research override (counts only, no text printed).

1. **Contents.** One loose CSV, `hate_speech_gener2_newF.csv` (4,541,167 bytes, sha256 `0ff85632aa3cc958896f812aad639186048162b22ade1f5d6c63633ee6bf0474`) with 16 header columns.
2. **What it appears to be.** Its **first nine columns** (`text, hate_label, source, profanity_score, language, dataset_version, combined_date, text_length, word_count`) match `combined_hate_speech_dataset.csv` in Shardul Dhekane's Kaggle dataset "Code-Mixed Hinglish Hate Speech Detection Dataset" (version 1, 2025-09-11) exactly.
   - The local **file name** matches no published file.
   - Its **seven extra columns** (`sentiment, emotion, Text, Style, Sentiment, Emotion, Unnamed: 4`) appear in no published file found. The duplicated names and the stray `Unnamed: 4` look like a merge of two tables.
   - The name fragment `gener2` suggests generation. The extra columns, and possibly some rows, may be machine-generated.

   So this is registered as a **local modified derivative of unknown provenance**, not as the upstream dataset.
   - **Local census (label values only, 2026-09-11):** 15,000 rows carry `hate_label` 1.0 (7,500) or 0.0 (7,500), all with `language = english` and `source = english_dataset`. These are the aggregate's **English** part, not Hindi or Hinglish. The other 3,201 rows have no label, language or source and come from the merged second table; the adapter excludes them.
3. **Proposed SAHAY-AI use.** None approved. At most an unofficial probe of how Hinglish abusive language passes through the pipeline, after human review.
4. **Label mapping.**
   - `hate_label` is **not** continuing threat, intimidation or coercion without contextual human review.
   - `profanity_score` is not severity, an SVI value or a band.
   - The local sentiment, emotion and style columns must **never** be treated as human labels.
   - `ml/data/label_firewall.py` refuses every mapping into a SAHAY target.
5. **Languages and modality.** The upstream aggregate covers Hindi, English and Hinglish, but **the labelled local rows are all `english`**. The row-level `language` column is used, never guessed. No audio, so D4 is structurally unavailable.
6. **Splits.** None published; no split column.
7. **Licence and provenance.**
   - The upstream uploader declares MIT (Kaggle's default licence link) for an aggregate of four sources: a hate-speech TSV, a profanity list, a Hindi dataset and an English dataset. Their own licences are not given.
   - An aggregator's MIT declaration does not cover the sources it compiles, and cannot cover columns later added by an unknown party.
   - Who produced the local file, and how, is not recorded.
8. **Collection and consent.** Social-media text of unknown origin; no consent statement.
9. **Personal-data and sensitive-content risk.**
   - Highly offensive, sexual and identity-targeted slurs.
   - It may name or tag real targets (not inspected).
   - Never print, log, commit, upload or show to a victim.
10. **Bias.** Hate-speech corpora over-represent particular dialects and communities as offensive; any probe must be reviewed by people competent in Hindi-English code-switching.
11. **Duplicates and leakage.** An aggregate of four sources may contain the same text more than once; the adapter marks exact and near duplicates.
12. **Contamination versus current fixtures.** Hinglish abusive vocabulary may overlap SAHAY threat and coercion lexicons. Register any row viewed during rule design.
13. **Redistribution and derived text.** Unknown, so **not permitted**. Only aggregate counts and hashes may appear.
14. **Current approval state.** `licence_pending`. No EXT decision exists.
15. **Before any use.**
    - Identification of the local file's origin.
    - Confirmation that it contains no generated text, or removal of what does.
    - The four upstream sources' licences.
    - Publisher confirmation of the `hate_label` encoding. The census shows 1.0 and 0.0; 1.0 is read as hate from the column name.
    - An approved EXT decision and `approved_for_research`.
16. **Never.** The locked or blind corpus, a threat or danger label source, D4, the SVI, or victim-facing output.
17. **References.**
    - https://www.kaggle.com/datasets/sharduldhekane/code-mixed-hinglish-hate-speech-detection-dataset
    - https://www.kaggle.com/datasets/sharduldhekane/code-mixed-hinglish-hate-speech-detection-dataset/croissant/download (Kaggle metadata, read-only)

    Accessed 2026-09-11.

**Approved uses:** none.

**Permitted handling today:** registry metadata and checksum verification. With the per-run local exploratory research override only: local conversion into a quarantined research artefact and an `external_exploratory_analysis` run (exploratory firing rates only), with outputs beneath `<SAHAY_DATASETS_ROOT>`. Never product, demo, tuning or evaluation data. Local offline experimental training is authorised only under EXT-119 (`ml/training/README.md`): the dataset stays `licence_pending` and quarantined, and weights derived from it stay private and out of every backend, frontend, mobile or victim-facing component.

**Sensitivity flags:** `real_user_generated_text`, `minors_possible`, `personal_names_not_reliably_redacted`. Private research only; never MVP, product or demo data.
