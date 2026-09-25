"""Speech emotion recognition (plan step M12): pinned backbones, fetch and verification.

Nothing here loads a model or touches the network on import. Model weights live beneath
``SAHAY_MODELS_ROOT``, never in Git. Affect output is namespaced ``affect:<class>``. It never
reaches the crisis pre-check, routing, hard overrides, forced bands or the victim client. It
may reach D4 only under decision D-8, after the promotion gate passes.
"""

AFFECT_CLASSES = ("neutral", "happy", "sad", "angry", "fearful")

#: emotion2vec+ native label -> SAHAY affect class; None = abstain for that clip (never folded).
E2V_TO_AFFECT = {
    "angry": "angry", "fearful": "fearful", "happy": "happy", "neutral": "neutral", "sad": "sad",
    # "<unk>" is the checkpoint's own token (tokens.txt); the model card calls it "unknown".
    "disgusted": None, "surprised": None, "other": None, "<unk>": None,
}
