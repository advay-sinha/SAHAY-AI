"""Text-affect shadow branch (plan M12f; D-9a, EXT-123): MuRIL / XLM-R on transcripts.

Nothing here loads a model or touches the network on import. Output is a 5-class
``affect:<class>`` probability for the local ML demonstration only (shadow). It never reaches
the crisis pre-check, routing, hard overrides, forced bands, the SVI, D4 or the victim client.
Product use is D-9b and stays off until its conditions are met.
"""

AFFECT_CLASSES = ("neutral", "happy", "sad", "angry", "fearful")
