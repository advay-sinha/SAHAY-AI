"""emotion2vec+ offline load check (run point R1). Run ONLY inside the isolated sahay-ser-e2v env.

    <sahay-ser-e2v>\\Scripts\\python -m ml.ser.e2v_check [--device cuda:0|cpu]

The check loads the pinned emotion2vec+ large checkpoint from its local directory with every
network connection blocked and FunASR's update check disabled. It then runs one forward pass on
a **synthetic** signal (a harmonic tone plus noise; no speech) to prove that the model loads and
returns well-formed output. It reports only: load status, parameter count, the label list,
embedding size, peak VRAM, time and blocked network attempts. Predictions on a synthetic tone
mean nothing and are not printed.

A failure here is deferral trigger X3 (install) or X4 (offline load) in the plan.
"""

import argparse
import importlib
import json
import sys
import time
from typing import Any, Dict, List, Optional

from ..runtime import config
from ..runtime.offline import network_blocked
from . import E2V_TO_AFFECT
from .models import get, load_manifest, model_dir

SAMPLE_RATE = 16000


def _synthetic(seconds: float = 3.0) -> Any:
    np = importlib.import_module("numpy")
    rng = np.random.default_rng(0)
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    x = 0.2 * np.sin(2 * np.pi * 140 * t) + 0.1 * np.sin(2 * np.pi * 280 * t) + 0.01 * rng.standard_normal(t.size)
    return x.astype(np.float32)


def check(root: Any, device: str) -> Dict[str, Any]:
    entry = get(load_manifest(), "emotion2vec_plus_large")
    directory = model_dir(root, entry)
    files = config.verify_files(directory, entry["files"], full_hash=False)
    if not files["ok"]:
        return {"status": "unavailable", "reason": "model files missing or wrong size; run ml.ser.models fetch"}
    torch = importlib.import_module("torch")
    report: Dict[str, Any] = {"device": device, "torch": torch.__version__}
    with network_blocked() as net:
        funasr = importlib.import_module("funasr")
        report["funasr"] = getattr(funasr, "__version__", "unknown")
        if device.startswith("cuda"):
            torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        model = funasr.AutoModel(model=str(directory), device=device, disable_update=True)
        report["load_seconds"] = round(time.perf_counter() - t0, 2)
        inner = getattr(model, "model", None)
        report["parameter_count"] = sum(p.numel() for p in inner.parameters()) if inner is not None else None
        t1 = time.perf_counter()
        out = model.generate(_synthetic(), granularity="utterance", extract_embedding=True)
        report["forward_seconds_3s_clip"] = round(time.perf_counter() - t1, 3)
        report["network_attempts_blocked"] = net["attempts"]
    first = out[0] if isinstance(out, list) and out else {}
    labels: List[str] = [str(l).split("/")[-1] for l in first.get("labels", [])]
    feats = first.get("feats")
    report["native_labels"] = labels
    report["labels_match_manifest"] = labels == entry["native_labels"] or sorted(labels) == sorted(entry["native_labels"])
    report["labels_all_mapped"] = all(l in E2V_TO_AFFECT for l in labels)
    report["embedding_dim"] = int(getattr(feats, "shape", [0])[-1]) if feats is not None else None
    if device.startswith("cuda"):
        report["peak_vram_mib"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
    report["status"] = "ok" if (labels and report["embedding_dim"] and report["network_attempts_blocked"] == 0) \
        else "check_failed"
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.ser.e2v_check", description=__doc__.split("\n")[0])
    parser.add_argument("--models-root", default=None)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args(argv)
    try:
        report = check(config.models_root(args.models_root), args.device)
    except Exception as exc:  # report the type only: no paths, no inputs
        report = {"status": "failed", "error_type": type(exc).__name__}
    print(json.dumps(report, indent=1))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
