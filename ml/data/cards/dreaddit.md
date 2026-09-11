# Dataset card — Dreaddit

Registry id `dreaddit`. **Status: `licence_pending`. No use is approved.** Checked on 2026-09-11, from authoritative sources only; the archive was inspected by metadata only.

1. **Contents.** English Reddit posts, segmented, with a binary *stress* label. The local archive holds 2 CSV members (a train file and a test file), 1,348,791 bytes, declaring 3,480,950 bytes uncompressed. The paper reports about 187k unlabelled posts and 3,553 labelled segments from 3,000 posts.
2. **Original task.** Binary stress identification in long-form social-media text.
3. **Proposed SAHAY-AI use.** Proposal only (EXT-105, P2): possibly a comparison baseline for a generic "stress expressed in text" signal. Nothing is implemented.
4. **Label mapping.** "Stress" means the author expresses mental or emotional strain with negative affect. It is **not** crisis or self-harm (D2), immediate danger (D1), vulnerability, SVI, a band, or a diagnosis, and it must never be treated as equivalent to any of them. There is no mapping to SAHAY labels.
5. **Languages and modality.** English text only. No Hindi, no Hinglish, no audio.
6. **Size and structure.** Paper: 2,838 train and 715 test segments. Local: 2 CSV files in a flat archive. Row counts were not read locally.
7. **Licence and provenance.** No dataset licence was found in the paper, on the ACL Anthology page or on the first author's page. The ACL Anthology CC BY 4.0 notice covers the *paper*. The paper's stated download location is the first author's Columbia University page. The posts are Reddit content subject to Reddit's terms. **The licence is unresolved.**
8. **Collection and consent.** Collected with PRAW from 10 subreddits across 5 domains (abuse, anxiety, financial, PTSD, social), January 2017 to November 2018. Labels came from Amazon Mechanical Turk: at least 5 annotators per segment, Fleiss κ 0.47. No consent, anonymisation or ethics statement was found.
9. **Personal-data and sensitive-content risk.** High. These are real first-person posts from domestic-violence, survivors-of-abuse, PTSD and anxiety communities, and public posts can be re-identified by searching their text. The content must never be printed, logged, committed, sent to an external service or shown to a victim.
10. **Bias.** Reddit users are mostly English-speaking and outside India. The domain differs from caste-atrocity helpline calls. The crowd annotators are unknown.
11. **Splits.** A train/test split is published; there is no validation split.
12. **Duplicates and leakage.** Segments from the same post may fall in different splits (not verified). Posts are public, so any model trained on the web may have seen them.
13. **Contamination versus current fixtures.** Low textual overlap: different language and domain. Once viewed during rule development, the data can never be holdout.
14. **Redistribution.** Unknown, so treat it as **not permitted**.
15. **Derived text in Git, models or reports.** **Not permitted.** Only aggregate counts and hashes may appear.
16. **Current approval state.** `licence_pending`. The external decision EXT-105 is **PROPOSED**, not approved, although a copy exists locally.
17. **Before training.** All of the following are required:
    - a verified licence or written terms permitting it;
    - an approved EXT decision;
    - a human licence review, with the registry moved to `approved_for_training`;
    - a privacy review of identifiers;
    - a documented reason why stress data serves a SAHAY task.
18. **Before evaluation.** The same licence and EXT gates, plus `approved_for_evaluation`, a stated metric purpose, and a contamination record. It can **never** be the official locked test set: `official_locked_test_allowed = false`.
19. **Limitations.** English, Reddit, crowd labels, moderate agreement. Not clinically validated.
20. **References.**
    - https://aclanthology.org/D19-6213/ (doi:10.18653/v1/D19-6213)
    - https://arxiv.org/abs/1911.00133
    - https://ar5iv.labs.arxiv.org/html/1911.00133
    - https://www.cs.columbia.edu/~eturcan/

    All accessed 2026-09-11.

**Approved uses:** none.

**Permitted handling today:** registry metadata, checksum and ZIP-directory audit only.

**Prohibited uses:**
- training, evaluation or threshold tuning;
- use as the locked test set;
- SVI dimension population;
- substituting for crisis or danger labels;
- diagnosis;
- redistribution or commercial use;
- victim-facing output;
- uploading to any external service;
- committing derived text.
