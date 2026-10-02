"""Advisory model signals for officers (EXT-133, PC-14).

Called from the background assessment cycle, never from the reply path. The
result is advisory and uncalibrated: it never changes routing, the band, the
SVI, alerts, the crisis interrupt or anything said to the victim, and it is
published to executive and supervisor sockets only.

Providers:
  mock            no signal (default); the console shows nothing
  local_service   the ML-owned loopback signal service on the laptop
  remote          the project's Hugging Face Space (hosted demo)

Whatever a provider returns is rebuilt from a fixed allowlist of labels and
fields, so nothing unexpected can pass through to the console.
"""

from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence

from .llm import _post_json, call_space

SHOWN_LABELS = ("crisis_self_harm", "communication_safety_coercion", "legal_urgency")
STATUSES = ("loaded", "unavailable", "failed")


class SignalProvider(Protocol):
    name: str

    def signals(self, texts: Sequence[str]) -> Optional[Dict[str, Any]]:
        ...


class MockSignals:
    name = "mock"

    def signals(self, texts: Sequence[str]) -> Optional[Dict[str, Any]]:
        return None


class LocalServiceSignals:
    name = "local_service"

    def __init__(self, base_url: str, timeout_s: float) -> None:
        self.base_url, self.timeout_s = base_url.rstrip("/"), timeout_s

    def signals(self, texts: Sequence[str]) -> Optional[Dict[str, Any]]:
        return sanitize(_post_json(f"{self.base_url}/signals", {"texts": list(texts)}, self.timeout_s))


class RemoteSpaceSignals:
    name = "remote"

    def __init__(self, space_url: str, token: str, key: str, timeout_s: float) -> None:
        self.space_url, self.token, self.key, self.timeout_s = space_url.rstrip("/"), token, key, timeout_s

    def signals(self, texts: Sequence[str]) -> Optional[Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        return sanitize(call_space(self.space_url, "signals", [list(texts), self.key], headers, self.timeout_s))


def sanitize(raw: Any) -> Optional[Dict[str, Any]]:
    """Rebuild a PC-14 payload from allowlisted fields only; None if unusable."""
    if not isinstance(raw, Mapping) or raw.get("status") not in STATUSES:
        return None
    labels: Dict[str, Dict[str, Any]] = {}
    for name in SHOWN_LABELS:
        item = (raw.get("labels") or {}).get(name)
        if not isinstance(item, Mapping):
            continue
        p = item.get("probability")
        if isinstance(p, (int, float)) and not isinstance(p, bool) and 0.0 <= float(p) <= 1.0:
            labels[name] = {"probability": round(float(p), 4), "fired": item.get("fired") is True}
    return {
        "status": raw["status"],
        "model": "experimental_shadow_classifier",
        "checkpoint_status": str(raw.get("checkpoint_status") or "rejected_for_product_integration")[:64],
        "advisory": True,
        "uncalibrated": True,
        "labels": labels if raw["status"] == "loaded" else {},
    }


def with_flag(signal: Optional[Dict[str, Any]], rules_crisis: bool) -> Optional[Dict[str, Any]]:
    """Add `flag`: the model fired on crisis language the rules did not catch.

    The flag asks an officer to review. It can only add caution, never remove it.
    """
    if signal is None:
        return None
    fired = bool(signal["labels"].get("crisis_self_harm", {}).get("fired"))
    return {**signal, "flag": fired and not rules_crisis}


def get_signal_provider(name: str) -> SignalProvider:
    if name == "mock":
        return MockSignals()
    from ..core.config import get_settings

    settings = get_settings()
    if name == "local_service":
        return LocalServiceSignals(settings.SIGNALS_SERVICE_URL, settings.SIGNALS_TIMEOUT_SECONDS)
    if name == "remote":
        return RemoteSpaceSignals(settings.LLM_REMOTE_URL, settings.LLM_API_KEY, settings.LLM_REMOTE_KEY,
                                  settings.SIGNALS_TIMEOUT_SECONDS)
    raise ValueError(f"signal provider {name!r} is not available")


def victim_texts(turns: List[Mapping[str, Any]]) -> List[str]:
    return [str(t["text"]) for t in turns if t.get("speaker") == "victim" and str(t.get("text", "")).strip()][-40:]
