"""Lazy text-encoder adapter: MuRIL (primary) and XLM-RoBERTa (comparison).

Both are **unfine-tuned for SAHAY labels**. The adapter returns token statistics and
mean-pooled encoder representations only. It never attaches a classification head, never
emits a label, probability, band, score or crisis flag, and nothing in the SAHAY pipeline
reads its output. The deterministic pipeline stays authoritative.

Loading happens only on ``load()``, only from the verified local directory, with the Hugging
Face offline switches set and ``local_files_only=True``. Inputs are never logged, and an
inference failure reports its exception type, never the text.
"""

import importlib
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import config, device as dev
from .offline import apply_offline_env
from .status import AVAILABLE, LOADED, UNAVAILABLE, RuntimeFailure, RuntimeStatus, redact

ENCODER_ROLES = {
    "muril_base_cased": "primary_text_encoder",
    "xlm_roberta_base": "comparison_text_encoder",
}
ALIASES = {"muril": "muril_base_cased", "xlmr": "xlm_roberta_base", "xlm-r": "xlm_roberta_base"}
MAX_BATCH = 16
MAX_TOKENS = 512
UNFINE_TUNED = "unfine-tuned for SAHAY labels: representations only, no prediction"


@dataclass
class TokenStats:
    token_count: int
    unknown_tokens: Optional[int]
    characters: int

    @property
    def unknown_rate(self) -> Optional[float]:
        if self.unknown_tokens is None or not self.token_count:
            return None
        return self.unknown_tokens / self.token_count

    @property
    def tokens_per_character(self) -> float:
        return self.token_count / self.characters if self.characters else 0.0


@dataclass
class EncoderOutput:
    model: str
    role: str
    device: str
    precision: str
    degraded: bool
    pooling: str
    dimension: int
    embeddings: List[List[float]]
    token_counts: List[int]
    truncated: List[bool]
    note: str = UNFINE_TUNED
    fine_tuned_for_sahay: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        """Aggregate-only view: safe to print."""
        d = asdict(self)
        d.pop("embeddings")
        d["batch"] = len(self.embeddings)
        return d


def resolve_id(name: str) -> str:
    logical = ALIASES.get(name, name)
    if logical not in ENCODER_ROLES:
        raise RuntimeFailure("invalid_input", "not a text encoder")
    return logical


# --- the real backend (transformers + torch); imported only on load ------------------------------


class HFEncoderBackend:
    """Transformers ``AutoModel`` without any task head, on CUDA FP16 or CPU FP32."""

    def __init__(self, directory: Path, choice: dev.DeviceChoice) -> None:
        apply_offline_env()
        self.torch = dev.import_torch()
        transformers = importlib.import_module("transformers")
        transformers.logging.set_verbosity_error()  # its load report prints absolute local paths
        transformers.logging.disable_progress_bar()
        self.choice = choice
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(str(directory), local_files_only=True)
        dtype = self.torch.float16 if choice.precision == "float16" else self.torch.float32
        # add_pooling_layer=False: the checkpoints carry no trained pooler, and a randomly
        # initialised layer must never exist, let alone be used.
        self.model = transformers.AutoModel.from_pretrained(
            str(directory), local_files_only=True, dtype=dtype, add_pooling_layer=False)
        self.model.eval().to(choice.device)
        self.unk_id = self.tokenizer.unk_token_id

    def token_ids(self, texts: Sequence[str], max_length: int) -> List[List[int]]:
        enc = self.tokenizer(list(texts), add_special_tokens=True, truncation=False)
        return [list(ids) for ids in enc["input_ids"]]

    def embed(self, texts: Sequence[str], max_length: int) -> List[List[float]]:
        torch = self.torch
        enc = self.tokenizer(list(texts), padding=True, truncation=True, max_length=max_length, return_tensors="pt")
        enc = {k: v.to(self.choice.device) for k, v in enc.items()}
        with torch.inference_mode():
            hidden = self.model(**enc).last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
        return pooled.float().cpu().tolist()

    def close(self) -> None:
        self.model = None
        self.tokenizer = None


BackendFactory = Callable[[Path, dev.DeviceChoice], Any]


class TextEncoder:
    def __init__(self, model: str, *, models_root: Optional[str] = None, device: str = "auto",
                 backend_factory: Optional[BackendFactory] = None, manifest: Optional[Dict[str, Any]] = None,
                 device_choice: Optional[dev.DeviceChoice] = None) -> None:
        self.logical_id = resolve_id(model)
        self.role = ENCODER_ROLES[self.logical_id]
        self._root_arg = models_root
        self._device = device
        self._choice = device_choice
        self._factory = backend_factory or HFEncoderBackend
        self._manifest = manifest
        self._backend: Any = None
        self.load_seconds: Optional[float] = None

    # --- status (never loads anything) ---

    def _entry(self) -> Dict[str, Any]:
        manifest = self._manifest if self._manifest is not None else config.load_manifest()
        return config.get_model(manifest, self.logical_id)

    def _directory(self) -> Path:
        root = config.models_root(self._root_arg)
        return config.model_dir(root, self._entry())

    def status(self) -> RuntimeStatus:
        if self._backend is not None:
            return RuntimeStatus(self.logical_id, LOADED, self.role, self._choice.device, self._choice.precision,
                                 self._choice.degraded)
        try:
            directory = self._directory()
        except config.RuntimeConfigError as exc:
            return RuntimeStatus(self.logical_id, UNAVAILABLE, str(exc))
        check = config.verify_files(directory, self._entry()["files"], full_hash=False)
        if not check["ok"]:
            return RuntimeStatus(self.logical_id, UNAVAILABLE, "model files missing or incomplete")
        if self._factory is HFEncoderBackend and not (dev.package_available("torch")
                                                      and dev.package_available("transformers")):
            return RuntimeStatus(self.logical_id, UNAVAILABLE, "runtime packages not installed in this environment")
        return RuntimeStatus(self.logical_id, AVAILABLE, self.role)

    # --- lifecycle ---

    @property
    def loaded(self) -> bool:
        return self._backend is not None

    def load(self) -> RuntimeStatus:
        if self._backend is not None:
            return self.status()
        state = self.status()
        if state.state != AVAILABLE:
            raise RuntimeFailure("unavailable", state.reason)
        directory = self._directory()
        choice = self._choice or dev.select_device(self._device)
        started = time.perf_counter()
        try:
            self._backend = self._factory(directory, choice)
        except Exception as exc:
            self._backend = None
            dev.release()
            code = "resource_exhausted" if dev.is_out_of_memory(exc) else "load_failed"
            raise RuntimeFailure(code, redact(str(exc), directory.parent.parent), exc) from None
        self._choice = choice
        self.load_seconds = time.perf_counter() - started
        return self.status()

    def unload(self) -> None:
        backend, self._backend = self._backend, None
        if backend is not None:
            backend.close()
            del backend
        dev.release()

    # --- inference ---

    @staticmethod
    def _check_texts(texts: Sequence[str]) -> List[str]:
        if isinstance(texts, str) or not isinstance(texts, (list, tuple)) or not texts:
            raise RuntimeFailure("invalid_input", "texts must be a non-empty list of strings")
        if not all(isinstance(t, str) and t.strip() for t in texts):
            raise RuntimeFailure("invalid_input", "every text must be a non-empty string")
        return list(texts)

    def _require_loaded(self) -> Any:
        if self._backend is None:
            raise RuntimeFailure("unavailable", "encoder is not loaded; call load() explicitly")
        return self._backend

    def token_stats(self, texts: Sequence[str]) -> List[TokenStats]:
        backend = self._require_loaded()
        texts = self._check_texts(texts)
        try:
            ids = backend.token_ids(texts, MAX_TOKENS)
        except Exception as exc:
            raise RuntimeFailure("inference_failed", "tokenisation", exc) from None
        unk = getattr(backend, "unk_id", None)
        return [TokenStats(len(row), None if unk is None else sum(1 for i in row if i == unk), len(t))
                for row, t in zip(ids, texts)]

    def encode(self, texts: Sequence[str], max_length: int = 256) -> EncoderOutput:
        backend = self._require_loaded()
        texts = self._check_texts(texts)
        if not 1 <= max_length <= MAX_TOKENS:
            raise RuntimeFailure("invalid_input", f"max_length must be 1..{MAX_TOKENS}")
        vectors: List[List[float]] = []
        counts: List[int] = []
        try:
            for start in range(0, len(texts), MAX_BATCH):  # bounded batching
                batch = texts[start:start + MAX_BATCH]
                vectors += backend.embed(batch, max_length)
                counts += [len(row) for row in backend.token_ids(batch, MAX_TOKENS)]
        except Exception as exc:
            if dev.is_out_of_memory(exc):
                self.unload()
                raise RuntimeFailure("resource_exhausted", "encoder released after out-of-memory", exc) from None
            raise RuntimeFailure("inference_failed", "encoder", exc) from None
        return EncoderOutput(
            model=self.logical_id, role=self.role, device=self._choice.device, precision=self._choice.precision,
            degraded=self._choice.degraded, pooling="attention-masked mean of last_hidden_state",
            dimension=len(vectors[0]) if vectors else 0, embeddings=vectors, token_counts=counts,
            truncated=[c > max_length for c in counts])
