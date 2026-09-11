# Dataset card — hinglish sentiment analysis (Kaggle)

Registry id `hinglish_sentiment_kaggle`. **Status: `licence_pending`. No use is approved.** Checked on 2026-09-11 from public Kaggle metadata. Local processing happens only through the owner-authorised local exploratory research override (`ml/data/README.md` §10), as private research that cannot enter the product or demo.

1. **Contents.** One header-less CSV, `FinalTrainingOnly.csv` (1,304,470 bytes, sha256 `50596b3ec7506916fda5f1d08148c649e570012eafdbf27a4da02d13ab215c80`). It has 14,594 rows of three fields: an original row index, the text, and a class.
2. **Identification.** Kaggle "hinglish sentiment analysis" by Ankit Lakra, version 1, published 2024-04-10. The evidence:
   - its metadata lists exactly `FinalTrainingOnly.csv` with three fields;
   - the "field names" in that metadata are the file's first data row, which matches the local first row by SHA-256 (compared without printing).

   Strongly supported, not confirmed by the publisher.
3. **Proposed SAHAY-AI use.** None approved. At most an unofficial probe of romanised Hindi, spelling variation and code-switching.
4. **Label mapping.** Class ∈ {0: 4,252, 1: 5,473, 2: 4,869}. **What each class means is not published**, so no polarity is assumed.
   - The adapter keeps only `source:hinglish_sentiment_kaggle:<value>` with family `sentiment_unspecified`.
   - A sentiment class is never safety, vulnerability, a band, the SVI, D4 or routing, and the label firewall refuses each of those.
5. **Languages and modality.** Romanised text, source-declared as Hinglish; the script is counted per record. No audio, so D4 is structurally unavailable.
6. **Splits.** The file name says training only. No test file and no split column exist.
7. **Licence and provenance.** The uploader declares Apache 2.0. The origin of the text is not described, so whether the uploader held rights in it is unknown. Redistribution and commercial use are recorded as unknown.
8. **Privacy.** Social-media text of undocumented origin; political and communal content is present. URLs, e-mails, handles, phone numbers and long numbers are redacted; personal names are not detected. Never print, log, commit, upload or show to a victim.
9. **Contamination.** Romanised Hindi overlaps the SAHAY Hinglish lexicons. Register any row viewed during rule design.
10. **Never.** The locked or blind corpus, training, any evaluation claim beyond `external_exploratory_analysis` exploratory firing rates, or victim-facing output.
11. **References.**
    - https://www.kaggle.com/datasets/ankitlakra24/hinglish-sentiment-analysis
    - https://www.kaggle.com/datasets/ankitlakra24/hinglish-sentiment-analysis/croissant/download

    Accessed 2026-09-11.

**Approved uses:** none. **Local exploratory research override:** eligible, per run, with the acknowledgement sentence; private research only, never product or demo data.

**Sensitivity flags:** `real_user_generated_text`, `minors_possible`, `personal_names_not_reliably_redacted`. Private research only; never MVP, product or demo data.
