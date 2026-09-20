"""Local model runtime: lazy adapters for MuRIL, XLM-R, Whisper Small and Silero VAD.

Importing this package, or any module in it, loads no model and imports no deep-learning
package. Models load only on an explicit ``load()`` call, only from files already present
beneath ``SAHAY_MODELS_ROOT``, and never over the network.

Nothing here decides anything. The encoders are unfine-tuned for SAHAY labels and return
representations only; Whisper returns a transcript; Silero returns speech intervals. No
output of this package feeds routing, the SVI, a band, D4 or the crisis pre-check, and no
application module imports it (``ml/tests/test_model_runtime.py`` enforces both).
"""
