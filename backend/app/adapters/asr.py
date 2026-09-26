"""Speech-recognition adapter (EXT-120, contract change PC-11).

The backend never loads a speech model. With ``ASR_PROVIDER=mock`` (the default) nothing needs
to be running. With ``ASR_PROVIDER=local_service`` it posts the uploaded audio to the ML-owned
speech-to-text process at ``ASR_SERVICE_URL``, which listens on 127.0.0.1 only and runs
voice-activity detection before recognition.

The adapter returns the transcript plus console-only measurements. Everything except
``status`` and ``text`` stays on the server: the victim client never receives confidence,
audio quality or prosody (root CLAUDE.md invariant 3).
"""

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Mapping, Optional, Protocol

#: Statuses the speech-to-text process can return for a readable request.
ASR_STATUSES = ("transcribed", "no_speech", "audio_unreadable")
#: Fields forwarded from the service; anything else it sends is dropped.
_KEPT = ("status", "text", "lang", "duration_s", "speech_s", "asr_confidence", "low_asr_confidence",
         "quality", "poor_audio", "prosody", "prosody_reasons", "timings_ms")


class ASRUnavailable(Exception):
    """The speech-to-text process is not reachable or failed. The endpoint answers 503."""


class ASRRejected(Exception):
    """The speech-to-text process refused the request (size, length, type or language)."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status, self.code = status, code


class ASRProvider(Protocol):
    name: str

    async def transcribe(self, audio: bytes, content_type: str, lang: str) -> Dict[str, Any]:
        ...


def _clean(payload: Mapping[str, Any]) -> Dict[str, Any]:
    out = {k: payload.get(k) for k in _KEPT if k in payload}
    if out.get("status") not in ASR_STATUSES:
        raise ASRUnavailable("unexpected response from the speech-to-text process")
    out["text"] = str(out.get("text") or "") if out["status"] == "transcribed" else ""
    return out


class MockASR:
    """Deterministic stand-in. Returns the queued responses in order, then ``no_speech``."""

    name = "mock"

    def __init__(self, responses: Optional[list] = None) -> None:
        self._responses = list(responses or [])
        self.calls = 0

    async def transcribe(self, audio: bytes, content_type: str, lang: str) -> Dict[str, Any]:
        self.calls += 1
        if self._responses:
            item = self._responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return _clean({"lang": lang, **item})
        return _clean({"status": "no_speech", "text": "", "lang": lang})


class LocalServiceASR:
    """Posts the audio to the loopback speech-to-text process in a worker thread."""

    name = "local_service"

    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _post(self, audio: bytes, content_type: str, lang: str) -> Dict[str, Any]:
        request = urllib.request.Request(f"{self.base_url}/transcribe?lang={lang}", data=audio, method="POST",
                                         headers={"Content-Type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as resp:
                return _clean(json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 413, 415):
                try:
                    code = json.loads(exc.read().decode("utf-8")).get("error", "rejected")
                except Exception:
                    code = "rejected"
                raise ASRRejected(exc.code, str(code)) from None
            raise ASRUnavailable(f"speech-to-text process error {exc.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ASRUnavailable(type(exc).__name__) from None

    async def transcribe(self, audio: bytes, content_type: str, lang: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._post, audio, content_type, lang)


def get_provider(settings: Any) -> ASRProvider:
    if settings.ASR_PROVIDER == "mock":
        return MockASR()
    if settings.ASR_PROVIDER == "local_service":
        return LocalServiceASR(settings.ASR_SERVICE_URL, settings.ASR_TIMEOUT_SECONDS)
    raise ValueError(f"ASR provider {settings.ASR_PROVIDER!r} is not available")
