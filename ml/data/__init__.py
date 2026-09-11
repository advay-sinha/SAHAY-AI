"""External-dataset governance: registry, archive safety and audit tooling.

Standard library only. Nothing in this package is imported by the dialogue,
guardrail, SVI or assessment code, and nothing here reads dataset CONTENT:
it hashes archives, reads ZIP central directories and enforces governance.
"""
