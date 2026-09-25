# Dataset card — RAVDESS (Audio_Speech_Actors_01-24)

Registry id `ravdess_audio_speech`. **Status: `metadata_pending`, not downloaded. EXT-003 APPROVED 2026-09-24 for SER training and evaluation.** Facts checked 2026-09-24 against the Zenodo record API (EXT-128 lookup).

1. **Contents.** 1,440 speech WAV files (per the publisher): 24 professional actors (12 female, 12 male), 2 fixed English statements, 8 emotions (neutral, calm, happy, sad, angry, fearful, disgust, surprised), with 2 intensities for every emotion except neutral. Only `Audio_Speech_Actors_01-24.zip` is approved: 208,468,073 bytes, md5 `bc696df654c87fed845eb13823edef8a`. The video and song files are excluded.
2. **SAHAY use (plan M12).** SER training, and validation on actor-disjoint splits. Only these classes are used: `affect:neutral|happy|sad|angry|fearful`. Calm, surprised and disgust are dropped.
3. **Label mapping.** Acted emotion categories are **not** distress, crisis, danger, vulnerability, an SVI, a band or a diagnosis. They reach D4 only through the D-8 mapping, and only after the promotion gate passes on team recordings. Until then `d4_acoustic_distress` stays prohibited.
4. **Licence.** CC BY-NC-SA 4.0: non-commercial use, attribution, share-alike. SAHAY policy is never to redistribute the audio, derived features or fine-tuned weights.
5. **Risks and limits.**
   - English only, acted, studio quality, with 2 fixed sentences, so it is a poor match for distressed Hindi phone speech. The gate therefore relies on team recordings.
   - Voices are identifiable actors. Audio is never committed, logged or shown to anyone.
6. **Contamination.** emotion2vec+ may have seen this corpus in training, so its numbers on it are labelled `possibly_seen_in_pretraining`. WavLM Base+ did not see it.
7. **Integrity (run R1).** `python -m ml.data.ser_audio fetch-ravdess` checks the size and md5, records the sha256, inspects the archive safely, then extracts and counts the WAV files.
8. **Citation.** Livingstone SR, Russo FA (2018). PLoS ONE 13(5): e0196391.
9. **References.** https://zenodo.org/records/1188976 · https://creativecommons.org/licenses/by-nc-sa/4.0/ (accessed 2026-09-24).

**Approved uses:** none until R1 verification passes and the record moves to `approved_for_training` in a reviewed change.
