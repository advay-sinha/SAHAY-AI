---
name: dataset-governance
description: Select, approve, register, prepare and evaluate datasets/models without leaking media into Git or overstating validity.
---

# Dataset governance

1. Read `docs/DATASETS_AND_SERVICES.md` and `docs/EXTERNAL_DECISIONS.md`.
2. Before download, require an APPROVED entry covering the exact dataset/model, release, scope and purpose.
3. Confirm source, licence, cost/access, size and checksum. If any is unclear, stop and ask.
4. Store raw and processed data under `DATA_ROOT`, outside Git.
5. Commit only manifests, attribution, checksums, scripts and aggregate evaluation results.
6. Never ingest real victim/NHAA data for the MVP.
7. Preserve raw originals. Derive 16 kHz mono PCM16 copies only after the conversion tool is approved.
8. Split training/evaluation by speaker and keep the final scripted scenario set locked.
9. Double-annotate high-consequence labels and adjudicate disagreements.
10. Describe public/synthetic/acted corpora as workflow or capability evidence, never clinical validity.
11. Record limitations by language, domain, recording condition and label source.
12. Never download a broader corpus when a selected subset satisfies the task.
