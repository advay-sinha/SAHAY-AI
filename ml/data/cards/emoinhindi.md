# Dataset card — EmoInHindi

Registry id `emoinhindi`. **Status: `licence_pending`. No use is approved.** Checked on 2026-09-11, from authoritative sources only; the archive was inspected by metadata only.

1. **Contents.** Hindi conversational TEXT. The paper reports 1,814 dialogues and 44,247 utterances, each utterance annotated with one or more emotions and an intensity.
   - The local archive holds **one CSV and one Markdown file** in an `EmoInHindi/` folder: 1,195,294 bytes, declaring 11,734,723 bytes uncompressed.
   - No member has an audio file extension (judged from the ZIP directory; member contents were not read).
   - It therefore stays at `corpus/text/hindi/emoinhindi/` and was **not moved** to an audio folder.
2. **Original task.** Multi-label emotion and intensity recognition in dialogues.
3. **Proposed SAHAY-AI use.** Proposal only: possibly a Hindi text resource for studying emotion vocabulary in counselling-style dialogue. Nothing is implemented.
4. **Label mapping.** The 16 emotion classes and 0–3 intensity are emotion labels. They are not vulnerability, crisis, danger, diagnosis or SVI labels. **They cannot populate D4:** D4 is *acoustic* distress, and this dataset has no audio. Even an audio emotion dataset would need an approved mapping and validation study (`ml/data/proposals/d4-acoustic-distress-evaluation.md`).
5. **Languages and modality.** Hindi text. Whether the text is in Devanagari, romanised or mixed script is **not verified**, because the content was not read.
6. **Size and structure.** See item 1. Whether the CSV carries a split column is not verified.
7. **Licence and provenance.**
   - The publisher's resource page (IIT Patna AI-NLP-ML group) says the resources are for research purposes only and must be cited. Access is through a request form. No named licence is given, and redistribution is not addressed.
   - The arXiv CC BY-NC-ND 4.0 and ACL Anthology CC BY 4.0 notices cover the *paper*, not the data.
   - Whether the local copy was obtained through that form, accepting its terms, is **not recorded**.
8. **Collection and consent.** Dialogues were created Wizard-of-Oz style by trained annotators playing roles in mental-health and legal counselling scenarios for crime victims (per the paper). No explicit consent or ethics-approval statement was found.
9. **Personal-data and sensitive-content risk.** Sensitive topics: domestic violence, harassment, fraud and cybercrime. The personas are described as simulated, but that is not verified against the content. The content must never be printed, logged, committed, sent to an external service or shown to a victim.
10. **Bias.** Simulated dialogues by a small annotator group; no demographic information is published. The register may differ from real distressed callers.
11. **Splits.** Paper: 80% train (20% of which is held for validation) and 20% test.
12. **Duplicates and leakage.** Utterances within a dialogue are correlated, so splits must be made at dialogue level. Not verified locally.
13. **Contamination versus current fixtures.** Topical overlap with SAHAY scenarios (crime-victim counselling). Any sample viewed during rule development can never be holdout.
14. **Redistribution.** Not addressed by the publisher, so treat it as **not permitted**. Commercial use is not permitted (research only).
15. **Derived text in Git, models or reports.** **Not permitted.** Only aggregate counts and hashes may appear.
16. **Current approval state.** `licence_pending`. **No EXT decision exists** in `docs/EXTERNAL_DECISIONS.md`.
17. **Before training.** All of the following are required:
    - confirmation that the copy was obtained under the publisher's terms;
    - a human licence review confirming that a government-helpline prototype is "research";
    - an approved EXT decision;
    - `approved_for_training`;
    - dialogue-level splits;
    - a privacy check.
18. **Before evaluation.** The same gates, plus `approved_for_evaluation` and a contamination record. It is never the official locked test set and never a D4 source.
19. **Limitations.** Text only, simulated dialogues, emotion rather than vulnerability labels. Not clinically validated.
20. **References.**
    - https://aclanthology.org/2022.lrec-1.627/
    - https://arxiv.org/abs/2205.13908
    - https://ar5iv.labs.arxiv.org/html/2205.13908
    - https://www.iitp.ac.in/~ai-nlp-ml/resources.html

    All accessed 2026-09-11.

**Approved uses:** none.

**Permitted handling today:** registry metadata and checksum verification. With the per-run local exploratory research override only: local conversion into a quarantined research artefact and an `external_exploratory_analysis` run (exploratory firing rates only), with outputs beneath `<SAHAY_DATASETS_ROOT>`. Never product, demo, training, tuning or evaluation data.

**Prohibited uses:**
- training, evaluation or threshold tuning;
- use as the locked test set;
- SVI or D4 population;
- substituting for crisis or danger labels;
- diagnosis;
- redistribution or commercial use;
- victim-facing output;
- uploading to any external service;
- committing derived text.

**Sensitivity flags:** `personal_names_not_reliably_redacted` (simulated per the paper, not verified). Private research only; never MVP, product or demo data.
