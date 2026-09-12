"""Task 7 (EXT-119): local MuRIL domain adaptation and the experimental SAHAY shadow classifier.

This package trains; it never decides. Stage A adapts MuRIL with masked-language modelling on the
private EXT-119 corpus built by ``ml.data.training_corpus``. Stage B fits source-namespaced
auxiliary heads as isolated diagnostics. Stage C trains ``experimental_shadow_classifier``, a
multi-label head over the eight schema detector categories, on private fictional records only.

Nothing here reads a dataset directly, and nothing imports Torch or Transformers at module import.
Every artefact lives beneath ``SAHAY_TRAINING_ROOT`` outside Git. No application module
imports this package, and the trained model never alters routing, crisis handling, evidence links,
SVI, D4, guardrails or victim-facing wording (EXT-119, Invariant 8 clarification).
"""
