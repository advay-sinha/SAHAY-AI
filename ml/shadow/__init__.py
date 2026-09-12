"""The experimental shadow classifier and its local ML-only demonstration (EXT-119).

``experimental_shadow_classifier`` is a MuRIL encoder with one multi-label head over the eight
schema detector categories, trained on fictional development data. It is **shadow output only**:
the deterministic pipeline (crisis pre-check, heuristic detectors, SVI, routing) stays
authoritative, and nothing here can change routing, crisis handling, evidence links, SVI, D4,
guardrails or victim-facing wording.

Under the EXT-119 Invariant 8 clarification these weights are for private ML research and an
operator-run local demonstration only. No backend, frontend, mobile or other victim-facing
component may import, load or call this package. Importing it loads no model and no Torch.
"""
