"""Hardware diagnostic: aggregate facts only, no paths, no serial numbers.

    python -m ml.runtime.hardware
"""

import importlib
import json
import platform
import subprocess
import sys
from typing import Any, Dict, Optional

from . import config, device as dev

_NVSMI_FIELDS = "name,driver_version,memory.total,memory.free,memory.used,compute_cap"


def nvidia_smi() -> Optional[Dict[str, str]]:
    try:
        out = subprocess.run(["nvidia-smi", f"--query-gpu={_NVSMI_FIELDS}", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    first = out.splitlines()[0] if out else ""
    values = [v.strip() for v in first.split(",")]
    keys = ["name", "driver_version", "memory_total_mib", "memory_free_mib", "memory_used_mib", "compute_capability"]
    return dict(zip(keys, values)) if len(values) == len(keys) else None


def report(models_root: Optional[str] = None) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "nvidia_smi": nvidia_smi(),
        "torch": None,
    }
    if dev.package_available("torch"):
        torch = dev.import_torch()
        t: Dict[str, Any] = {"version": torch.__version__, "cuda_build": torch.version.cuda,
                             "cuda_available": torch.cuda.is_available()}
        if t["cuda_available"]:
            props = torch.cuda.get_device_properties(0)
            free, total = torch.cuda.mem_get_info()
            t.update({"device": props.name, "capability": f"{props.major}.{props.minor}",
                      "vram_total_mib": round(total / 2**20), "vram_free_mib": round(free / 2**20),
                      "cudnn": torch.backends.cudnn.version()})
        info["torch"] = t
    for name in ("transformers", "ctranslate2", "faster_whisper", "silero_vad", "huggingface_hub", "numpy"):
        if dev.package_available(name):
            mod = importlib.import_module(name)
            info.setdefault("packages", {})[name] = getattr(mod, "__version__", "installed")
    if dev.package_available("psutil"):
        psutil = importlib.import_module("psutil")
        info["ram_total_mib"] = round(psutil.virtual_memory().total / 2**20)
        info["ram_available_mib"] = round(psutil.virtual_memory().available / 2**20)
        try:
            root = config.models_root(models_root)
            info["models_root_free_gib"] = round(psutil.disk_usage(str(root)).free / 2**30, 1)
        except config.RuntimeConfigError as exc:
            info["models_root_free_gib"] = None
            info["models_root_state"] = str(exc)
    return info


def main(argv: Optional[list] = None) -> int:
    print(json.dumps(report(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
