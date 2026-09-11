"""Device selection, memory measurement and cleanup. Torch is imported only when asked for.

CUDA is used only when it is actually available; otherwise the adapter falls back to CPU and
says so with ``degraded=True``. Timings synchronise CUDA first, benchmarks reset the peak
counters first, and an out-of-memory error is turned into a clean ``resource_exhausted``
failure after the model is released.
"""

import gc
import importlib
import importlib.util
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

DEVICE_CHOICES = ("auto", "cuda", "cpu")


@dataclass(frozen=True)
class DeviceChoice:
    device: str          # "cuda" or "cpu"
    precision: str       # "float16" or "float32"
    degraded: bool
    reason: str


def package_available(name: str) -> bool:
    """Whether a package is importable, without importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def import_torch() -> Any:
    return importlib.import_module("torch")


def select_device(requested: str = "auto", torch_module: Any = None) -> DeviceChoice:
    """Pick CUDA FP16 when safely available, else CPU FP32 marked degraded."""
    if requested not in DEVICE_CHOICES:
        raise ValueError(f"device must be one of {DEVICE_CHOICES}")
    if requested == "cpu":
        return DeviceChoice("cpu", "float32", False, "cpu_requested")
    torch = torch_module if torch_module is not None else (import_torch() if package_available("torch") else None)
    cuda_ok = False
    if torch is not None:
        try:
            cuda_ok = bool(torch.cuda.is_available()) and torch.cuda.device_count() > 0
        except Exception:  # a broken driver must degrade, not crash
            cuda_ok = False
    if cuda_ok:
        return DeviceChoice("cuda", "float16", False, "cuda_available")
    return DeviceChoice("cpu", "float32", True, "cuda_unavailable_cpu_fallback")


def is_out_of_memory(exc: BaseException) -> bool:
    if type(exc).__name__ in ("OutOfMemoryError", "MemoryError"):
        return True
    return "out of memory" in str(exc).lower()


def synchronize(torch: Any, device: str) -> None:
    if device == "cuda":
        torch.cuda.synchronize()


def reset_peak(torch: Any, device: str) -> None:
    if device == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()


def cuda_memory(torch: Any, device: str) -> Dict[str, Optional[float]]:
    """Torch-allocator peaks plus device-wide free/total (the latter also sees CTranslate2)."""
    if device != "cuda":
        return {"peak_allocated_mb": None, "peak_reserved_mb": None, "device_free_mb": None, "device_total_mb": None}
    free, total = torch.cuda.mem_get_info()
    return {
        "peak_allocated_mb": round(torch.cuda.max_memory_allocated() / 2**20, 1),
        "peak_reserved_mb": round(torch.cuda.max_memory_reserved() / 2**20, 1),
        "device_free_mb": round(free / 2**20, 1),
        "device_total_mb": round(total / 2**20, 1),
    }


def device_free_mb(torch: Any = None) -> Optional[float]:
    torch = torch if torch is not None else (import_torch() if package_available("torch") else None)
    if torch is None or not torch.cuda.is_available():
        return None
    free, _ = torch.cuda.mem_get_info()
    return round(free / 2**20, 1)


def process_rss_mb() -> Optional[float]:
    if not package_available("psutil"):
        return None
    psutil = importlib.import_module("psutil")
    return round(psutil.Process().memory_info().rss / 2**20, 1)


def release(torch: Any = None) -> None:
    """Collect garbage and hand cached CUDA blocks back to the driver."""
    gc.collect()
    if torch is None:
        torch = sys.modules.get("torch")  # never import torch just to clean up
    if torch is not None:
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass
