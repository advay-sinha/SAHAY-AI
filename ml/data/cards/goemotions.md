# Dataset card — GoEmotions

Registry id `goemotions`. **Status: `metadata_pending`, not downloaded. EXT-125 APPROVED 2026-09-24 for shadow text-affect training only.** Facts checked 2026-09-24: the licence against the Hugging Face dataset card, the sizes by HEAD request.

1. **Contents.** English Reddit comments labelled with 27 emotions plus neutral (multi-label), in the upstream simplified train/dev/test TSV splits. Sizes on 2026-09-24: 3,519,053, 439,059 and 436,706 bytes, plus `emotions.txt` at 248 bytes. The source is a branch, not a pinned release, so the sha256 is recorded at first fetch and verified after that.
2. **SAHAY use (plan M12e–f).** English training data for the MuRIL and XLM-R **shadow** text-affect branch. Anger, fear, sadness, joy and neutral map to `affect:<class>`. It is never a SAHAY safety label, and it never feeds the product D4 unless every D-9b condition is met.
3. **Licence.** Apache-2.0, as stated on the dataset card. It must be confirmed against the repository before any product use (D-9b condition a).
4. **Risks.** Real user-generated text: the publisher masked names as `[NAME]`, but other identifiers may remain, and minors may be among the authors. Text is never printed, committed, logged or shown to a victim.
5. **Citation.** Demszky D et al. (2020). GoEmotions: A Dataset of Fine-Grained Emotions. ACL 2020.
6. **References.** https://huggingface.co/datasets/google-research-datasets/go_emotions · https://github.com/google-research/google-research/tree/master/goemotions (accessed 2026-09-24).

**Approved uses:** none until it is fetched, verified and moved to `approved_for_training` (shadow scope) in a reviewed change.
