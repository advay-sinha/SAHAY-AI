"""Guardrailed phrasing with a local language model (EXT-132).

``prompt`` is pure (standard library only). ``service`` runs the model in the
private ``sahay-ml-models`` environment and listens on loopback only; it is
imported by nothing in the application.
"""
