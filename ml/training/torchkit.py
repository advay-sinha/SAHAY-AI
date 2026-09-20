"""Shared Torch helpers for the three stages. Nothing heavy is imported at module import.

Torch, Transformers and NumPy are imported through ``importlib`` only when a stage runs, so the
default test suite and every application module stay free of them. Loading is offline: Hugging
Face offline switches, ``local_files_only=True`` and, in the CLI, an active socket block.
"""

import importlib
import json
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from ..runtime import config as rc
from ..runtime.offline import apply_offline_env
from . import paths

BASE_MODEL = "muril_base_cased"
PACKAGES = ("torch", "transformers", "safetensors", "tokenizers", "numpy", "accelerate")


def torch() -> Any:
    return importlib.import_module("torch")


def transformers() -> Any:
    apply_offline_env()
    tf = importlib.import_module("transformers")
    tf.logging.set_verbosity_error()  # its load reports print absolute local paths
    tf.logging.disable_progress_bar()
    return tf


def seed_everything(seed: int) -> None:
    t = torch()
    random.seed(seed)
    t.manual_seed(seed)
    t.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")


def device() -> str:
    t = torch()
    if not t.cuda.is_available():
        return "cpu"
    return "cuda"


def base_model_dir(models_root: Optional[str] = None) -> Dict[str, Any]:
    """The pinned MuRIL directory after a size check (full hashes are verified by the CLI preflight)."""
    manifest = rc.load_manifest()
    entry = rc.get_model(manifest, BASE_MODEL)
    root = rc.models_root(models_root)
    directory = rc.model_dir(root, entry)
    check = rc.verify_files(directory, entry["files"], full_hash=False)
    if not check["ok"]:
        raise RuntimeError("the pinned MuRIL files are missing or incomplete; nothing is downloaded")
    return {"dir": directory, "revision": entry["revision"], "repo": entry["upstream_repo"], "entry": entry}


def load_tokenizer(directory: Path) -> Any:
    return transformers().AutoTokenizer.from_pretrained(str(directory), local_files_only=True)


def package_versions() -> Dict[str, str]:
    out = {}
    meta = importlib.import_module("importlib.metadata")
    for name in PACKAGES:
        try:
            out[name] = meta.version(name)
        except Exception:
            out[name] = "absent"
    return out


def gpu_temperature() -> Optional[int]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        return int(out.splitlines()[0])
    except Exception:
        return None


class Monitor:
    """Peak VRAM, process RAM and GPU temperature, sampled cheaply."""

    def __init__(self) -> None:
        self.max_temp: Optional[int] = None
        self.max_rss_mb: float = 0.0
        self.started = time.perf_counter()
        t = torch()
        if t.cuda.is_available():
            t.cuda.reset_peak_memory_stats()

    def sample(self) -> None:
        temp = gpu_temperature()
        if temp is not None:
            self.max_temp = max(self.max_temp or 0, temp)
        try:
            psutil = importlib.import_module("psutil")
            self.max_rss_mb = max(self.max_rss_mb, psutil.Process().memory_info().rss / 2**20)
        except Exception:
            pass

    def report(self) -> Dict[str, Any]:
        t = torch()
        cuda = t.cuda.is_available()
        return {"seconds": round(time.perf_counter() - self.started, 1),
                "peak_allocated_mb": round(t.cuda.max_memory_allocated() / 2**20, 1) if cuda else None,
                "peak_reserved_mb": round(t.cuda.max_memory_reserved() / 2**20, 1) if cuda else None,
                "peak_rss_mb": round(self.max_rss_mb, 1), "max_gpu_temperature_c": self.max_temp}


def save_pretrained_atomic(model: Any, tokenizer: Any, target: Path, extra: Mapping[str, Any]) -> Dict[str, Any]:
    """Save weights as safetensors plus tokenizer into ``target`` via a .partial directory."""
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        _remove_tree(partial)
    partial.mkdir(parents=True)
    model.save_pretrained(str(partial), safe_serialization=True)
    if tokenizer is not None:
        tokenizer.save_pretrained(str(partial))
    hashes = {p.name: paths.sha256_file(p) for p in sorted(partial.iterdir()) if p.is_file()}
    paths.write_json(partial / "provenance.json", {**extra, "files_sha256": hashes})
    if target.exists():
        _remove_tree(target)
    os.replace(partial, target)
    return hashes


def _remove_tree(path: Path) -> None:
    for child in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        child.rmdir() if child.is_dir() else child.unlink()
    path.rmdir()


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def chunks(items: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]
