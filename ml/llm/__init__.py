"""Guardrailed phrasing with a local language model (EXT-132).

``prompt`` and ``meaning`` are pure (standard library only) and are what the
backend imports. The model itself runs in ``ml.runtime.phrase_service``, in the
private ``sahay-ml-models`` environment, on loopback only.
"""
