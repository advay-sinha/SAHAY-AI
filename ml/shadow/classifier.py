"""Lazy loader and inference for ``experimental_shadow_classifier``.

Two checkpoint sets exist, chosen explicitly:
- ``task7`` (the default), found through ``SAHAY_TRAINING_ROOT/checkpoints/stage-c/SELECTED.json``;
  its status is fixed at ``rejected_for_product_integration``;
- ``task7b``, found through ``SAHAY_TRAINING_ROOT/task7b/checkpoints/SELECTED.json``; its status
  comes from the private ``task7b/STATUS.json`` written by the promotion-gate evaluation.

If the root, pointer or files are missing, the result is an explicit ``unavailable`` status with no
probabilities: never zeros and never a "safe" reading. Malformed model output, a timeout or any
inference exception is a ``failed`` result reporting only the exception type. Inputs are never
logged.

Output is shadow output only: raw logits, sigmoid probabilities, fixed-0.5 development firings, the
checkpoint hash and the checkpoint status. It is uncalibrated and never authoritative. It has no
routing, band, SVI, D4, diagnosis, confidence or safety field and never sees an external source
label. No status, including ``candidate_for_human_review``, permits product integration.
"""

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..runtime import device as dev
from ..runtime.offline import apply_offline_env
from ..training import paths
from . import model as sm

AVAILABLE, LOADED, UNAVAILABLE, FAILED = "available", "loaded", "unavailable", "failed"
FORBIDDEN_KEYS = frozenset({"svi", "band", "d4", "routing", "route", "priority", "routed_critical", "diagnosis",
                            "needs_human", "safe", "source_label", "source_labels", "calibrated_confidence"})
CHECKPOINT_SETS = {"task7": ("checkpoints", "stage-c", "SELECTED.json"),
                   "task7b": ("task7b", "checkpoints", "SELECTED.json")}
REJECTED = "rejected_for_product_integration"
CANDIDATE = "candidate_for_human_review"
DEPLOYMENT_STATUSES = (REJECTED, CANDIDATE)
PRODUCT_NOTE = "Not approved for product integration"


class ShadowFailure(Exception):
    def __init__(self, code: str, cause: Optional[BaseException] = None) -> None:
        self.code = code
        super().__init__(code + (f" ({type(cause).__name__})" if cause is not None else ""))


@dataclass
class ShadowResult:
    model_id: str
    status: str
    reason: str = ""
    labels: List[str] = field(default_factory=lambda: list(sm.LABELS))
    logits: Optional[Dict[str, float]] = None
    probabilities: Optional[Dict[str, float]] = None
    development_firings: Optional[Dict[str, bool]] = None
    threshold: float = sm.THRESHOLD
    calibrated: bool = False
    authoritative: bool = False
    identity: str = sm.IDENTITY
    device: Optional[str] = None
    checkpoint_set: str = "task7"
    checkpoint_sha256: Optional[str] = None
    deployment_status: str = REJECTED
    promotion_gates_passed: Optional[bool] = False
    promotion_metrics_fully_evaluable: Optional[bool] = None
    product_integration: str = PRODUCT_NOTE

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def checkpoint_status(root: Path, checkpoint_set: str) -> Dict[str, Any]:
    """The recorded status of a checkpoint set. Anything unknown is treated as rejected."""
    if checkpoint_set == "task7":
        return {"deployment_status": REJECTED, "promotion_gates_passed": False}
    path = paths.confined(root, "task7b", "STATUS.json")
    if not path.is_file():
        return {"deployment_status": REJECTED, "promotion_gates_passed": None, "reason": "not evaluated"}
    data = json.loads(path.read_text(encoding="utf-8"))
    status = data.get("deployment_status")
    return {"deployment_status": status if status in DEPLOYMENT_STATUSES else REJECTED,
            "promotion_gates_passed": bool(data.get("promotion_gates_passed")),
            "promotion_metrics_fully_evaluable": bool(data.get("promotion_metrics_fully_evaluable"))}


class ShadowClassifier:
    def __init__(self, training_root: Optional[str] = None, device: str = "auto", loader: Any = None, *,
                 checkpoint_set: str = "task7", timeout_s: Optional[float] = None) -> None:
        if checkpoint_set not in CHECKPOINT_SETS:
            raise ValueError(f"checkpoint_set must be one of {tuple(CHECKPOINT_SETS)}")
        self._root_arg = training_root
        self._device = device
        self._loader = loader or sm.load
        self._set = checkpoint_set
        self._timeout = timeout_s
        self._bundle: Optional[Dict[str, Any]] = None
        self._choice: Optional[dev.DeviceChoice] = None
        self._hash: Optional[str] = None
        self._status: Dict[str, Any] = {"deployment_status": REJECTED, "promotion_gates_passed": False}

    def _checkpoint(self) -> Path:
        root = paths.training_root(self._root_arg)
        pointer = paths.confined(root, *CHECKPOINT_SETS[self._set])
        if not pointer.is_file():
            raise ShadowFailure("no selected shadow checkpoint")
        rel = json.loads(pointer.read_text(encoding="utf-8"))["checkpoint"]
        directory = paths.confined(root, *rel.split("/"))
        for name in (sm.CONFIG_FILE, sm.HEAD_FILE, sm.ENCODER_DIR):
            if not (directory / name).exists():
                raise ShadowFailure("selected shadow checkpoint is incomplete")
        return directory

    def _result(self, state: str, **kw: Any) -> ShadowResult:
        return ShadowResult(sm.MODEL_ID, state, checkpoint_set=self._set, checkpoint_sha256=self._hash,
                            deployment_status=self._status["deployment_status"],
                            promotion_gates_passed=self._status.get("promotion_gates_passed"),
                            promotion_metrics_fully_evaluable=self._status.get("promotion_metrics_fully_evaluable"),
                            **kw)

    def status(self) -> ShadowResult:
        if self._bundle is not None:
            return self._result(LOADED, device=self._choice.device if self._choice else None)
        try:
            self._checkpoint()
        except (paths.TrainingRootError, ShadowFailure) as exc:
            return self._result(UNAVAILABLE, reason=str(exc))
        if self._loader is sm.load and not (dev.package_available("torch") and dev.package_available("transformers")):
            return self._result(UNAVAILABLE, reason="runtime packages not installed in this environment")
        return self._result(AVAILABLE)

    @property
    def loaded(self) -> bool:
        return self._bundle is not None

    def load(self) -> ShadowResult:
        if self._bundle is None:
            state = self.status()
            if state.status != AVAILABLE:
                return state
            apply_offline_env()
            self._choice = dev.select_device(self._device)
            try:
                directory = self._checkpoint()
                self._bundle = self._loader(directory, self._choice.device)
                self._hash = paths.sha256_file(directory / sm.HEAD_FILE)
                self._status = checkpoint_status(paths.training_root(self._root_arg), self._set)
            except Exception as exc:
                self._bundle = None
                return self._result(FAILED, reason=f"load failed ({type(exc).__name__})")
        return self.status()

    def unload(self) -> None:
        self._bundle = None
        dev.release()

    def classify(self, turns: Sequence[Mapping[str, Any]]) -> ShadowResult:
        """Shadow output for one conversation (victim turns). Never raises for model errors."""
        if self._bundle is None:
            state = self.load()
            if state.status != LOADED:
                return state
        text = sm.model_text(turns)
        if not text:
            return self._result(UNAVAILABLE, reason="no victim text to classify")
        started = time.perf_counter()
        try:
            logits = self._infer([text])[0]
        except Exception as exc:  # the deterministic pipeline must never depend on this succeeding
            if dev.is_out_of_memory(exc):
                self.unload()
            return self._result(FAILED, reason=f"inference failed ({type(exc).__name__})")
        if self._timeout is not None and time.perf_counter() - started > self._timeout:
            return self._result(FAILED, reason="inference timed out")
        if (not isinstance(logits, (list, tuple)) or len(logits) != len(sm.LABELS)
                or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in logits)):
            return self._result(FAILED, reason="malformed model output")
        probs = [1.0 / (1.0 + math.exp(-x)) for x in logits]
        return self._result(LOADED, logits={n: round(float(x), 4) for n, x in zip(sm.LABELS, logits)},
                            probabilities={n: round(p, 4) for n, p in zip(sm.LABELS, probs)},
                            development_firings={n: p >= sm.THRESHOLD for n, p in zip(sm.LABELS, probs)},
                            device=self._choice.device if self._choice else None)

    def _infer(self, texts: Sequence[str]) -> List[List[float]]:
        """Raw logits per text. Test fakes may supply ``infer`` (probabilities) or ``infer_logits``."""
        b = self._bundle
        if "infer_logits" in b:
            return b["infer_logits"](texts)
        if "infer" in b:
            rows = b["infer"](texts)
            if not isinstance(rows, (list, tuple)):
                return rows
            return [[math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6))) if
                     isinstance(p, (int, float)) and not isinstance(p, bool) else p for p in row]
                    if isinstance(row, (list, tuple)) else row for row in rows]
        t, net, tok = b["torch"], b["net"], b["tokenizer"]
        device = self._choice.device if self._choice else "cpu"
        with t.inference_mode():
            enc = tok(list(texts), max_length=sm.MAX_LEN, truncation=True, padding=True, return_tensors="pt").to(device)
            return net(enc["input_ids"], enc["attention_mask"]).float().cpu().tolist()
