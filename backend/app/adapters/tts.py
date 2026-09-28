"""Voice output adapter (M13, EXT-103, PC-12).

The backend never loads a speech model. ``none`` (the default) produces no audio, so the client
shows the text. ``windows_voice`` uses the ML-owned wrapper around the built-in offline Windows
voices. Only assistant turns reach it, and an assistant turn exists only for text that passed
``guardrails.validate`` or is language-approved fallback text (turn_loop). Fixed scripts are
never synthesised: they come from approved human recordings through ``ml.tts.presynth``.
"""

import threading
from typing import Any, Optional

from ml.tts.synthesize import NullSynthesizer, SynthesisUnavailable, WindowsVoiceSynthesizer

__all__ = ["get_provider", "SynthesisUnavailable"]

_lock = threading.Lock()
_windows: Optional[WindowsVoiceSynthesizer] = None


def get_provider(settings: Any):
    """The configured synthesiser. The Windows worker is started once and reused."""
    global _windows
    if getattr(settings, "TTS_PROVIDER", "none") != "windows_voice":
        return NullSynthesizer()
    with _lock:
        if _windows is None:
            _windows = WindowsVoiceSynthesizer()
        return _windows
