"""LLM adapter (EXT-132).

The complete dialogue must run with LLM_PROVIDER=mock (root CLAUDE.md section 5).

The LLM only ever rewords a sentence the state machine already chose. It never
chooses a state, never picks a question, never sees the person's words, and its
output always passes guardrails.validate (and, in English, the meaning check)
before anyone sees it. Any error, timeout or empty reply returns None, and the
pre-written sentence is used.

Providers:
  mock            returns None: every turn uses its pre-written sentence (default)
  local_service   the ML-owned loopback phrasing service (see docs/LOCAL_SETUP.md)
  remote          the project's Hugging Face Space (hosted demo), HTTPS with a token

Live rewording is English only. In the first measured trial Hindi rewordings
drifted in meaning and took 7-13 s; Hindi and Hinglish use approved text.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Protocol

LIVE_REGISTERS = ("en",)


class LLMProvider(Protocol):
    name: str

    def phrase(self, intent: str, licensed_question: Optional[str], lang: str, *,
               register: Optional[str] = None, source: Optional[str] = None) -> Optional[str]:
        """Return a rewording of `source`, or None to use the pre-written sentence."""
        ...


class MockLLM:
    """Returns None, so every turn uses its pre-written fallback.

    This is the default. It makes the fallback path the tested path rather than
    an untested emergency route.
    """

    name = "mock"

    def phrase(self, intent: str, licensed_question: Optional[str], lang: str, *,
               register: Optional[str] = None, source: Optional[str] = None) -> Optional[str]:
        return None


def _post_json(url: str, payload: Dict[str, Any], timeout_s: float,
               headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


class LocalServiceLLM:
    """The loopback phrasing service. Failures are silent: the caller falls back."""

    name = "local_service"

    def __init__(self, base_url: str, timeout_s: float) -> None:
        self.base_url, self.timeout_s = base_url.rstrip("/"), timeout_s

    def phrase(self, intent: str, licensed_question: Optional[str], lang: str, *,
               register: Optional[str] = None, source: Optional[str] = None) -> Optional[str]:
        if register not in LIVE_REGISTERS or not source:
            return None
        reply = _post_json(f"{self.base_url}/phrase", {"source": source, "register": register}, self.timeout_s)
        text = (reply or {}).get("text")
        return text if isinstance(text, str) and text.strip() else None


class RemoteSpaceLLM:
    """The project's Hugging Face Space, through its Gradio HTTP API.

    Two calls: POST starts the job and returns an event id; GET streams the result as
    server-sent events. Both share one deadline. The token is sent as a bearer header
    and never logged; the Space also checks a shared key.
    """

    name = "remote"

    def __init__(self, space_url: str, token: str, key: str, timeout_s: float) -> None:
        self.space_url, self.token, self.key, self.timeout_s = space_url.rstrip("/"), token, key, timeout_s

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def phrase(self, intent: str, licensed_question: Optional[str], lang: str, *,
               register: Optional[str] = None, source: Optional[str] = None) -> Optional[str]:
        if register not in LIVE_REGISTERS or not source:
            return None
        return call_space(self.space_url, "phrase", [source, register, self.key], self._headers(), self.timeout_s)


def call_space(space_url: str, api_name: str, data: list, headers: Dict[str, str],
               timeout_s: float) -> Optional[Any]:
    """Run one Gradio API call and return its first output, or None on any failure."""
    import time

    deadline = time.monotonic() + timeout_s
    started = _post_json(f"{space_url}/gradio_api/call/{api_name}", {"data": data}, timeout_s, headers)
    event_id = (started or {}).get("event_id")
    if not isinstance(event_id, str):
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    request = urllib.request.Request(f"{space_url}/gradio_api/call/{api_name}/{event_id}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=remaining) as resp:
            event = None
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event == "complete":
                    out = json.loads(line[5:].strip())
                    return out[0] if isinstance(out, list) and out else None
                elif event == "error":
                    return None
                if time.monotonic() > deadline:
                    return None
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return None


def get_provider(name: str) -> LLMProvider:
    if name == "mock":
        return MockLLM()
    from ..core.config import get_settings

    settings = get_settings()
    if name == "local_service":
        return LocalServiceLLM(settings.LLM_SERVICE_URL, settings.LLM_TIMEOUT_SECONDS)
    if name == "remote":
        return RemoteSpaceLLM(settings.LLM_REMOTE_URL, settings.LLM_API_KEY, settings.LLM_REMOTE_KEY,
                              settings.LLM_TIMEOUT_SECONDS)
    raise ValueError(f"LLM provider {name!r} is not available")
