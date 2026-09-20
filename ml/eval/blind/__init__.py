"""Blind human-authored evaluation corpus: tooling only. Standard library only.

This package is the *infrastructure* for an independent Hindi / English /
Hinglish safety evaluation set. It contains no evaluation scenario, no label
and no human record, and it never creates one. Every official sample is
written by a named human author, annotated blind by named human reviewers and
stored OUTSIDE Git under the root named by ``SAHAY_EVAL_ROOT``.

Why the tooling and the corpus are separated
  The existing corpora (``ml/eval/corpus/dev.json``, ``candidates.json`` and
  the three red-team files) are exposed: every outcome was published in
  ``ml/eval/results/`` and several failures were read while designing the
  hardening rules. Measuring a fix on them reports REGRESSION performance, not
  evaluation performance. An independent number needs samples that neither the
  pipeline authors nor the code agent have ever seen — which means humans must
  write them, and this package must make that possible without ever touching
  the narratives it is guarding.

Prediction firewall
  No module in this package imports ``ml.assessment``, the detectors, the
  crisis pre-check, the SVI engine, the guardrail validator, the
  recommendation logic or a backend adapter. ``firewall.py`` states the list
  and ``ml/tests/test_blind_freeze.py`` proves it in a clean subprocess.
  Predictions may be produced only after a corpus is frozen, through the one
  lazy-import boundary in ``ml/eval/blind_evaluation.py::_pipeline``, which is
  reached only when every freeze, hash, ledger and state check has passed.

Module map
  exit_codes     the documented process exit codes
  paths          SAHAY_EVAL_ROOT resolution, private layout, path confinement
  normalize      deterministic text folding used for leakage comparison only
  plan           the versioned coverage plan and coverage accounting
  submission     the author-submission schema, content hash and PII screen
  leakage        deterministic contamination / similarity checks
  annotation     blinded review packets and the review-record schema
  assignment     the roster, deterministic assignment and conflict detection
  adjudication   the conflict-resolution record and its rules
  ledger         the append-only SHA-256 hash chain (shared with review_workflow)
  states         the corpus status workflow and its transition ledger
  freeze         the freeze gate and the artefacts a freeze produces
  adapter        frozen private schema -> the existing evaluator's sample shape
  results        evaluation-result validation, hashing and atomic publication
  firewall       the forbidden-module list and its assertion

Command-line entry points live one level up so the documented invocations stay
short: ``python -m ml.eval.blind_corpus`` and
``python -m ml.eval.blind_evaluation``.
"""
