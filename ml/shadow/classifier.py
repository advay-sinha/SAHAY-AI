"""Lazy loader and inference for ``experimental_shadow_classifier``.

The checkpoint is found only through ``SAHAY_TRAINING_ROOT/checkpoints/stage-c/SELECTED.json``.
If the root, the pointer or the files are missing, the result is an explicit ``unavailable``
status with no probabilities: never zeros, never a "safe" reading. Inputs are never logged; an
inference failure reports its exception type only.

Output is shadow output: probabilities per schema detector category and fixed-0.5 development
firings, labelled uncalibrated and non-authoritative. It has no routing, band, SVI, D4 or
diagnosis field, and it never sees or returns an external source label.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..runtime import device as dev
from ..runtime.offline import apply_offline_env
from ..training import paths
from . import model as sm

AVAILABLE, LOADED, UNAVAILABLE, FAILED = "available", "loaded", "unavailable", "failed"
FORBIDDEN_KEYS = frozenset({"svi", "band", "d4", "routing", "route", "priority", "routed_critical", "diagnosis",
                            "needs_human", "safe", "source_label", "source_labels"})


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
    probabilities: Optional[Dict[str, float]] = None
    development_firings: Optional[Dict[str, bool]] = None
    threshold: float = sm.THRESHOLD
    calibrated: bool = False
    authoritative: bool = False
    identity: str = sm.IDENTITY
    device: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ShadowClassifier:
    def __init__(self, training_root: Optional[str] = None, device: str = "auto", loader: Any = None) -> None:
        self._root_arg = training_root
        self._device = device
        self._loader = loader or sm.load
        self._bundle: Optional[Dict[str, Any]] = None
        self._choice: Optional[dev.DeviceChoice] = None

    def _checkpoint(self) -> Path:
        root = paths.training_root(self._root_arg)
        pointer = paths.confined(root, "checkpoints", "stage-c", "SELECTED.json")
        if not pointer.is_file():
            raise ShadowFailure("no selected shadow checkpoint")
        rel = json.loads(pointer.read_text(encoding="utf-8"))["checkpoint"]
        directory = paths.confined(root, *rel.split("/"))
        for name in (sm.CONFIG_FILE, sm.HEAD_FILE, sm.ENCODER_DIR):
            if not (directory / name).exists():
                raise ShadowFailure("selected shadow checkpoint is incomplete")
        return directory

    def status(self) -> ShadowResult:
        if self._bundle is not None:
            return ShadowResult(sm.MODEL_ID, LOADED, device=self._choice.device if self._choice else None)
        try:
            self._checkpoint()
        except (paths.TrainingRootError, ShadowFailure) as exc:
            return ShadowResult(sm.MODEL_ID, UNAVAILABLE, reason=str(exc))
        if self._loader is sm.load and not (dev.package_available("torch") and dev.package_available("transformers")):
            return ShadowResult(sm.MODEL_ID, UNAVAILABLE, reason="runtime packages not installed in this environment")
        return ShadowResult(sm.MODEL_ID, AVAILABLE)

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
                self._bundle = self._loader(self._checkpoint(), self._choice.device)
            except Exception as exc:
                self._bundle = None
                return ShadowResult(sm.MODEL_ID, FAILED, reason=f"load failed ({type(exc).__name__})")
        return self.status()

    def unload(self) -> None:
        self._bundle = None
        dev.release()

    def classify(self, turns: Sequence[Mapping[str, Any]]) -> ShadowResult:
        """Shadow probabilities for one conversation (victim turns). Never raises for model errors."""
        if self._bundle is None:
            state = self.load()
            if state.status != LOADED:
                return state
        text = sm.model_text(turns)
        if not text:
            return ShadowResult(sm.MODEL_ID, UNAVAILABLE, reason="no victim text to classify")
        try:
            probs = self._infer([text])[0]
        except Exception as exc:  # the deterministic pipeline must never depend on this succeeding
            if dev.is_out_of_memory(exc):
                self.unload()
            return ShadowResult(sm.MODEL_ID, FAILED, reason=f"inference failed ({type(exc).__name__})")
        return ShadowResult(sm.MODEL_ID, LOADED, probabilities={n: round(p, 4) for n, p in zip(sm.LABELS, probs)},
                            development_firings={n: p >= sm.THRESHOLD for n, p in zip(sm.LABELS, probs)},
                            device=self._choice.device if self._choice else None)

    def _infer(self, texts: Sequence[str]) -> List[List[float]]:
        b = self._bundle
        if "infer" in b:  # test fakes
            return b["infer"](texts)
        t, net, tok = b["torch"], b["net"], b["tokenizer"]
        device = self._choice.device if self._choice else "cpu"
        with t.inference_mode():
            enc = tok(list(texts), max_length=sm.MAX_LEN, truncation=True, padding=True, return_tensors="pt").to(device)
            return t.sigmoid(net(enc["input_ids"], enc["attention_mask"]).float()).cpu().tolist()
