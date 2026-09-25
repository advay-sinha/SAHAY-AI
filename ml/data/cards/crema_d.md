# Dataset card — CREMA-D (AudioWAV)

Registry id `crema_d`. **Status: `metadata_pending`; audio not present. EXT-104 APPROVED 2026-09-24 for AudioWAV only.** Facts checked 2026-09-24 from the local repository archive (LICENSE.txt and the LFS pointers).

1. **Contents.** 7,442 WAV clips, 605,899,936 bytes, summed from the local Git LFS pointers. There are 91 actors, 12 fixed English sentences and 6 emotions (anger, disgust, fear, happy, neutral, sad), with crowd-sourced perceptual ratings. Only `AudioWAV/` is approved; `AudioMP3` and `VideoFlash` are excluded.
2. **The local copy is pointers only.** The folder `CREMA-D-1.0/CREMA-D-1.0` is an extracted repository archive: every AudioWAV entry is a pointer (sha256 plus size), not audio, and the folder is not a git clone. `python -m ml.data.ser_audio snapshot-crema-pointers` records every pointer privately. The downloaded audio, from a fresh clone with `git lfs pull` or an approved mirror, is then verified file by file with `verify-crema`.
3. **SAHAY use (plan M12).** SER training and the cross-corpus check (train on CREMA-D, test on RAVDESS). Only `affect:neutral|happy|sad|angry|fearful` is used; disgust is dropped.
4. **Label mapping.** Same rule as for RAVDESS: never distress, crisis, danger, an SVI, a band or a diagnosis. It reaches D4 only via D-8 after the gate. `d4_acoustic_distress` stays prohibited until then.
5. **Licence.** Open Database License v1.0, per the repository's LICENSE.txt. SAHAY policy is never to redistribute.
6. **Risks and limits.** English only, acted, 12 fixed sentences, and the actors' voices are identifiable. It is not distressed-caller speech.
7. **Contamination.** emotion2vec+ may have seen this corpus (`possibly_seen_in_pretraining`). WavLM Base+ did not.
8. **Citation.** Cao H, Cooper DG, Keutmann MK, Gur RC, Nenkova A, Verma R (2014). IEEE Transactions on Affective Computing 5(4): 377-390.
9. **References.** https://github.com/CheyneyComputerScience/CREMA-D · https://opendatacommons.org/licenses/odbl/1-0/ (accessed 2026-09-24).

**Approved uses:** none until R1 verification passes and the record moves to `approved_for_training` in a reviewed change.
