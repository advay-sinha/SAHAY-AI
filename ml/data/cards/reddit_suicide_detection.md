# Dataset card — Suicide and Depression Detection (Kaggle)

Registry id `reddit_suicide_detection`. **Status: `licence_pending`. No use is approved.** Checked on 2026-09-11 from the public Kaggle metadata. Under the owner-authorised local exploratory research override the file was converted locally and sampled for an `external_exploratory_analysis` run (exploratory firing rates only); no text is printed, committed or reported, only aggregates.

1. **Contents.** English Reddit posts in one CSV (166,902,029 bytes, sha256 `1ec16b065a2fae36488de16e8abfc326586a576a25901e09467223e545ddd295`). The header has three columns: an unnamed index, `text` and `class`.
2. **Original task.** Binary classification of posts by the community they came from.
3. **Proposed SAHAY-AI use.** None approved. At most an unofficial English development probe of how crisis-vocabulary handling behaves on real social-media text, after licence, privacy and ethics review.
4. **Label mapping.** `class ∈ {suicide, non-suicide}` records the **subreddit of origin** (r/SuicideWatch → suicide, r/teenagers → non-suicide; the metadata says r/depression posts were labelled `depression` in version 13). It is a provenance label, not a human risk judgement:
   - it is **not** `crisis_self_harm` ground truth;
   - it is **not** `immediate_danger` ground truth;
   - `non-suicide` is **not** safe or no-alert ground truth;
   - it is **not** a diagnosis, a band, an SVI value or a D4 value.

   The adapter keeps it only as `source:reddit_suicide_detection:<value>`, and `ml/data/label_firewall.py` refuses every mapping into a SAHAY target.
5. **Languages and modality.** English text. No audio, so D4 is structurally unavailable.
6. **Size and structure.** One loose CSV; the Kaggle `archive.zip` was not kept, so archive safety could not be checked.
7. **Licence and provenance.**
   - Kaggle uploader: Nikhileswar Komati. Version 14, published 2021-01-04, modified 2021-05-19.
   - The uploader declares **CC BY-SA 4.0**. The uploader did not write the posts, and no grant from their authors, or from Reddit, is documented. A declaration by someone who does not hold the rights cannot license them.
   - The posts were collected with the Pushshift API. They remain subject to Reddit's User Agreement and API terms; Reddit revoked Pushshift's access in 2023.
   - Kaggle availability grants neither training nor redistribution rights.
8. **Collection and consent.** Public posts scraped without the authors' consent. No ethics review is described.
9. **Personal-data and sensitive-content risk.** **Severe.**
   - Real people's first-person writing about suicidal ideation and depression.
   - Verbatim public text can be searched and re-identified.
   - Usernames, links or other identifiers may be present; the adapter redacts URL, e-mail, Reddit-user, community, handle, phone and long-number shapes, but cannot detect personal names.
   - The non-suicide class comes from a teenagers' community, so many authors are likely to be minors.
   - The content must never be printed, logged, committed, uploaded, shown to a victim or used to draft victim-facing text.
10. **Bias.** Reddit users, predominantly English-speaking and not representative of Indian helpline callers; 2008–2021 register.
11. **Splits.** None published.
12. **Duplicates and leakage.** Reddit reposts and cross-posts are common; the adapter marks exact and near duplicates.
13. **Contamination versus current fixtures.** Crisis vocabulary overlaps the SAHAY crisis lexicon's domain. Any row viewed while designing a rule must be registered in `ml/eval/contamination.py` and can no longer serve as a regression probe.
14. **Redistribution.** Unknown, so treat it as **not permitted**.
15. **Derived text in Git, models or reports.** **Not permitted.** Only aggregate counts and hashes may appear.
16. **Current approval state.** `licence_pending`. No EXT decision exists in `docs/EXTERNAL_DECISIONS.md`.
17. **Before any use.** A rights review of the underlying posts, a privacy and minors review, an approved EXT decision, `approved_for_research`, and an ethics sign-off. Even then its labels need a separate human mapping record, and none is authorised.
18. **Never.** The locked or blind corpus, a crisis or danger label source, D4, the SVI, diagnosis, or victim-facing output.
19. **Limitations.** Subreddit labels, not annotation; English Reddit, not helpline intake; not clinically validated.
20. **References.**
    - https://www.kaggle.com/datasets/nikhileswarkomati/suicide-watch
    - https://www.kaggle.com/datasets/nikhileswarkomati/suicide-watch/croissant/download (Kaggle metadata, read-only)

    Accessed 2026-09-11.

**Approved uses:** none.

**Permitted handling today:** registry metadata and checksum verification. With the per-run local exploratory research override only: local conversion into a quarantined research artefact and an `external_exploratory_analysis` run (exploratory firing rates only), with outputs beneath `<SAHAY_DATASETS_ROOT>`. Never product, demo, tuning or evaluation data. Local offline experimental training is authorised only under EXT-119 (`ml/training/README.md`): the dataset stays `licence_pending` and quarantined, and weights derived from it stay private and out of every backend, frontend, mobile or victim-facing component.

**Invariant 8 and sensitivity.** Sensitivity flags: `real_user_generated_text`, `potential_victim_narratives`, `minors_possible`, `personal_names_not_reliably_redacted`. This dataset may contain authentic sensitive narratives; offline aggregation and redaction reduce exposure but do not make them simulated. It is accepted only as private, offline exploratory research and must never be used in the MVP, the product, the demo, training, tuning, the locked corpus or any official evaluation.
