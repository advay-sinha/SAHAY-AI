# Freeze manifests (content-free)

This directory is where the **only** committed artefact of a frozen blind evaluation corpus lives:
a content-free manifest per corpus version, written by

```powershell
python -m ml.eval.blind_corpus freeze --actor <person-id> --public-manifest ml/eval/blind/freeze_manifests/v1.json
```

A manifest here carries corpus version, plan version, freeze timestamp, sample count, the corpus
SHA-256, a per-file SHA-256, the language / category / slice totals, the reviewer-count summary and
the four ledger heads. It carries **no** scenario text, **no** label tied to a narrative, **no**
reviewer identity and **no** reviewer reasoning. Its purpose is to let a reader outside the private
root verify that a stated number was computed over a specific, unaltered corpus.

## The directory is empty, and that is correct

No corpus has been frozen. `ml/eval/corpus/locked.json` is empty, locked count is 0, and official
metrics are unavailable. Writing a manifest now would be a fabrication: it would assert hashes over
a corpus that does not exist and reviewer counts for reviews nobody recorded. The freeze gate
refuses on the coverage condition long before it could write one, and
`ml/tests/test_blind_freeze.py` asserts that a successful freeze of a temporary corpus does not
create a file here.

See `ml/eval/BLIND_EVALUATION.md`.
