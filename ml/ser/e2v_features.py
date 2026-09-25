"""emotion2vec+ feature cache (plan M12c, run R2b). Run ONLY in the isolated sahay-ser-e2v env.

    <sahay-ser-e2v>\\Scripts\\python -m ml.ser.e2v_features

This reads the trimmed 16 kHz clips written by ``ml.ser.preprocess audio`` and, for each
usable clip, stores:

    emotion2vec_plus_large/embeddings.npy   (N, 1024) float16 utterance embeddings
    emotion2vec_plus_large/scores.npy       (N, 9) float32 native class scores, in NATIVE_ORDER
    emotion2vec_plus_large/index.json       clip order, label order, revision, timings

beneath ``<SAHAY_TRAINING_ROOT>/ser/corpus-v1/``. The model is frozen and loaded from its
pinned local directory with every network connection blocked. Nothing is scored or evaluated
here: zero-shot and head evaluation happen in the training step (M12d). Only the ``train``
and ``val`` splits may ever influence a model choice. Numbers on RAVDESS and CREMA-D are
labelled ``possibly_seen_in_pretraining``.
"""

import argparse
import importlib
import io
import json
import sys
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..runtime import config
from ..runtime.offline import network_blocked
from . import E2V_TO_AFFECT
from .models import get, load_manifest, model_dir

CORPUS_DIR = ("ser", "corpus-v1")
TRAINING_ROOT_ENV = "SAHAY_TRAINING_ROOT"
NATIVE_ORDER = ("angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "<unk>")


class FeatureError(Exception):
    """A refusal with a fixed message: no path, no audio."""


def native_scores(labels: Sequence[str], scores: Sequence[float]) -> List[float]:
    """Reorder one clip's scores into NATIVE_ORDER. Labels may carry a ``中文/english`` prefix."""
    clean = [str(l).split("/")[-1] for l in labels]
    if sorted(clean) != sorted(NATIVE_ORDER):
        raise FeatureError("the model returned an unexpected label set")
    by = dict(zip(clean, (float(s) for s in scores)))
    return [by[name] for name in NATIVE_ORDER]


def _training_root(explicit: Optional[str]) -> Path:
    import os
    raw = explicit or os.environ.get(TRAINING_ROOT_ENV, "")
    if not raw.strip():
        raise FeatureError(f"{TRAINING_ROOT_ENV} is not set and no --training-root was given; it has no default")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise FeatureError(f"the directory named by {TRAINING_ROOT_ENV} does not exist")
    return root


def _read_wav(data: bytes) -> Any:
    np = importlib.import_module("numpy")
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1 or w.getframerate() != 16000:
            raise FeatureError("expected the trimmed 16 kHz mono 16-bit clips from ml.ser.preprocess")
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def run(models_root: Path, out: Path, device: str) -> Dict[str, Any]:
    np = importlib.import_module("numpy")
    torch = importlib.import_module("torch")
    features = out / "features.jsonl"
    if not features.is_file():
        raise FeatureError("features.jsonl is missing; run `python -m ml.ser.preprocess audio` first")
    rows = [json.loads(line) for line in features.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r.get("status") == "ok"]
    entry = get(load_manifest(), "emotion2vec_plus_large")
    directory = model_dir(models_root, entry)
    if not config.verify_files(directory, entry["files"], full_hash=False)["ok"]:
        raise FeatureError("emotion2vec+ files are missing or the wrong size")
    funasr = importlib.import_module("funasr")
    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    model = funasr.AutoModel(model=str(directory), device=device, disable_update=True, disable_pbar=True)
    emb = np.zeros((len(rows), 1024), dtype=np.float16)
    scores = np.zeros((len(rows), len(NATIVE_ORDER)), dtype=np.float32)
    started = time.perf_counter()
    for i, r in enumerate(rows):
        x = _read_wav((out / r["audio_rel"]).read_bytes())
        res = model.generate(x, granularity="utterance", extract_embedding=True, disable_pbar=True)[0]
        emb[i] = np.asarray(res["feats"], dtype=np.float32).reshape(-1)[:1024].astype(np.float16)
        scores[i] = native_scores(res["labels"], res["scores"])
        if (i + 1) % 500 == 0:
            print(json.dumps({"progress": i + 1, "of": len(rows), "seconds": round(time.perf_counter() - started, 1)}),
                  flush=True)
    target = out / "emotion2vec_plus_large"
    target.mkdir(parents=True, exist_ok=True)
    np.save(target / "embeddings.npy", emb)
    np.save(target / "scores.npy", scores)
    seconds = round(time.perf_counter() - started, 1)
    index = {"clip_ids": [r["clip_id"] for r in rows], "native_order": list(NATIVE_ORDER),
             "affect_map": {k: v for k, v in E2V_TO_AFFECT.items()}, "embedding_shape": list(emb.shape),
             "revision": entry["revision"], "contamination": "possibly_seen_in_pretraining (RAVDESS, CREMA-D)",
             "seconds": seconds}
    (target / "index.json").write_bytes((json.dumps(index, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    report = {"step": "emotion2vec", "clips": len(rows), "device": device, "seconds": seconds,
              "torch": torch.__version__, "funasr": getattr(funasr, "__version__", "unknown")}
    if device.startswith("cuda"):
        report["peak_vram_mib"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.ser.e2v_features", description=__doc__.split("\n")[0])
    parser.add_argument("--models-root", default=None)
    parser.add_argument("--training-root", default=None)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args(argv)
    out = _training_root(args.training_root).joinpath(*CORPUS_DIR)
    with network_blocked() as net:
        report = run(config.models_root(args.models_root), out, args.device)
        report["network_attempts_blocked"] = net["attempts"]
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "reports" / "emotion2vec.json").write_bytes((json.dumps(report, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps(report, indent=1))
    return 0 if net["attempts"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
