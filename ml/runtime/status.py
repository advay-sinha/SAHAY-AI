"""Runtime status, safe failures and the output firewall. Standard library only.

A missing or broken model is reported as an explicit state, never as a zero, an empty score
or a silent default. Failure messages are built from fixed codes plus the exception *type*;
they never carry an input sentence, a transcript, audio, an absolute path or a token.
"""

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

AVAILABLE = "available"          # files present and verified by size; not loaded
LOADED = "loaded"
UNAVAILABLE = "unavailable"      # root unset, files missing, or the runtime package is absent
FAILED = "failed"

#: Keys no runtime result may carry: this package never decides or scores anything.
FORBIDDEN_OUTPUT_KEYS = frozenset({
    "svi", "band", "d4", "dimension_scores", "crisis", "crisis_flag", "danger", "vulnerability", "routing",
    "priority", "needs_human", "alerts", "recommendation", "prediction", "predictions", "label", "labels",
    "probabilities", "logits", "score", "risk",
})
_TOKEN = re.compile(r"hf_[A-Za-z0-9]{8,}")
_WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/][^\s'\"]*")
_POSIX_PATH = re.compile(r"(?<![\w.])/(?:[^\s'\"/]+/)+[^\s'\"]*")


@dataclass(frozen=True)
class RuntimeStatus:
    model: str
    state: str
    reason: str = ""
    device: Optional[str] = None
    precision: Optional[str] = None
    degraded: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuntimeFailure(Exception):
    """A runtime failure with a fixed, safe message.

    ``code`` is one of: ``unavailable``, ``integrity_failed``, ``load_failed``, ``resource_exhausted``,
    ``inference_failed``, ``invalid_input``, ``unsupported_language``, ``unsupported_sample_rate``,
    ``network_blocked``.
    """

    def __init__(self, code: str, detail: str = "", cause: Optional[BaseException] = None) -> None:
        self.code = code
        self.cause_type = type(cause).__name__ if cause is not None else None
        text = code if not detail else f"{code}: {detail}"
        if self.cause_type:
            text += f" ({self.cause_type})"
        super().__init__(text)


def redact(message: str, root: Optional[Path] = None) -> str:
    """Strip tokens and paths from a load-time diagnostic. Never used on inference errors."""
    if root is not None:
        message = message.replace(str(root), "<SAHAY_MODELS_ROOT>")
    message = _TOKEN.sub("<token>", message)
    message = _WINDOWS_PATH.sub("<path>", message)
    message = _POSIX_PATH.sub("<path>", message)
    return message[:200]


def assert_no_decision_keys(result: Mapping[str, Any], where: str = "runtime result") -> None:
    """Refuse any result that carries a decision, score or prediction key, at any depth."""
    for key in _walk_keys(result):
        if key.lower() in FORBIDDEN_OUTPUT_KEYS:
            raise AssertionError(f"{where} carries forbidden key {key!r}")


def _walk_keys(obj: Any) -> Iterable[str]:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_keys(v)
