"""SER model training and evaluation (plan M12d, runs R3 and R4). Private model environment only.

    python -m ml.ser.train baseline      [--regime both|crema] [--seed N]   # prosody logistic regression
    python -m ml.ser.train whisper-head  [--regime ...]                    # frozen Whisper encoder + head
    python -m ml.ser.train e2v-zeroshot                                   # emotion2vec+ native head, no training
    python -m ml.ser.train e2v-head      [--regime ...]                    # frozen emotion2vec+ + head
    python -m ml.ser.train wavlm         [--regime ...] [--epochs N]       # WavLM Base+ fine-tune (GPU, long)
    python -m ml.ser.train compare                                        # table of every finished run

Protocol (fixed before any training, plan M12 / D-8):
  * splits are actor-disjoint; the best epoch is chosen on validation UAR only;
  * test splits are scored once, at the end, per corpus and per sex;
  * ``--regime crema`` trains on CREMA-D only and also scores all of RAVDESS (cross-corpus);
  * emotion2vec numbers are labelled ``possibly_seen_in_pretraining``;
  * the model that feeds D4 is chosen later, on the team-dev recordings (R6b), not here.

Everything runs offline with network connections blocked. Runs are written beneath
``<SAHAY_TRAINING_ROOT>/ser/runs/<model>-<regime>-s<seed>/``. Predictions carry clip ids and
probabilities only: no audio, and no text.
"""

import argparse
import copy
import importlib
import io
import json
import math
import sys
import time
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..runtime import config as rc
from ..runtime.offline import apply_offline_env, network_blocked
from . import E2V_TO_AFFECT
from . import data as sd
from . import metrics as sm
from .models import get as ser_get, load_manifest as ser_manifest, model_dir as ser_model_dir

CORPUS_DIR = ("ser", "corpus-v1")
RUNS_DIR = ("ser", "runs")
TRAIN_VERSION = "ser-train-1.0"
AFFECT = sd.AFFECT
SAMPLE_RATE = 16000


class TrainError(Exception):
    """A refusal with a fixed message: no path, no audio."""


def _torch() -> Any:
    return importlib.import_module("torch")


# --- evaluation sets ----------------------------------------------------------------------------


def eval_sets(rows: Sequence[Mapping[str, Any]], regime: str) -> Dict[str, List[int]]:
    """Named index sets: train and val (the regime's datasets), per-corpus test, and cross-corpus."""
    ds = sd.TRAIN_REGIMES[regime]
    sets = {"train": sd.select(rows, "train", ds), "val": sd.select(rows, "val", ds)}
    for d in ds:
        sets[f"test:{d}"] = sd.select(rows, "test", (d,))
    if regime == "crema":
        sets["cross:ravdess_audio_speech"] = [i for i, r in enumerate(rows) if r["dataset"] == "ravdess_audio_speech"]
    if not sets["train"] or not sets["val"]:
        raise TrainError("the training or validation split is empty")
    return sets


def score_sets(rows: Sequence[Mapping[str, Any]], sets: Mapping[str, List[int]], preds: Sequence[Optional[str]],
               evidence: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, idx in sets.items():
        if name == "train" or not idx:
            continue
        gold = [rows[i]["affect"] for i in idx]
        pred = [preds[i] for i in idx]
        res = sm.evaluate(gold, pred, AFFECT, evidence)
        res["by_sex"] = sm.by_group(gold, pred, [rows[i].get("sex", "unknown") for i in idx], AFFECT, evidence)
        out[name] = res
    return out


# --- generic head trainer (cached features) -------------------------------------------------------


def fit_head(model: Any, X: Any, y: Any, sets: Mapping[str, List[int]], weights: Sequence[float], *, epochs: int,
             lr: float, wd: float, batch: int, patience: int, seed: int, device: str) -> Dict[str, Any]:
    torch = _torch()
    tr, va = sets["train"], sets["val"]
    model = model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32, device=device))
    gen = torch.Generator().manual_seed(seed)
    Xtr, ytr = X[tr], y[tr]
    best = {"uar": -1.0, "epoch": -1, "state": None}
    history = []
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(tr), generator=gen)
        total = 0.0
        for s in range(0, len(tr), batch):
            idx = perm[s:s + batch]
            opt.zero_grad()
            loss = loss_fn(model(Xtr[idx].to(device)), ytr[idx].to(device))
            loss.backward()
            opt.step()
            total += loss.item() * len(idx)
        preds = predict_labels(model, X[va], device)
        uar = sm.evaluate([AFFECT[int(i)] for i in y[va]], preds, AFFECT)["uar"] or 0.0
        history.append({"epoch": epoch, "train_loss": round(total / len(tr), 5), "val_uar": uar})
        if uar > best["uar"]:
            best = {"uar": uar, "epoch": epoch, "state": copy.deepcopy(model.state_dict())}
        elif epoch - best["epoch"] >= patience:
            break
    model.load_state_dict(best["state"])
    return {"model": model, "best_epoch": best["epoch"], "best_val_uar": best["uar"], "history": history}


def predict_probs(model: Any, X: Any, device: str, batch: int = 512) -> Any:
    torch = _torch()
    model.eval()
    outs = []
    with torch.inference_mode():
        for s in range(0, len(X), batch):
            outs.append(torch.softmax(model(X[s:s + batch].to(device)).float(), dim=-1).cpu())
    return torch.cat(outs)


def predict_labels(model: Any, X: Any, device: str) -> List[str]:
    return [AFFECT[int(i)] for i in predict_probs(model, X, device).argmax(dim=-1)]


# --- models ---------------------------------------------------------------------------------------


def _layer_weighted_head(n_layers: int, dim: int, hidden: int = 256, dropout: float = 0.2) -> Any:
    torch = _torch()
    nn = torch.nn

    class LayerWeightedHead(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.layer_logits = nn.Parameter(torch.zeros(n_layers))
            self.net = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, hidden), nn.ReLU(), nn.Dropout(dropout),
                                     nn.Linear(hidden, len(AFFECT)))

        def forward(self, x: Any) -> Any:  # x: (B, L, D)
            w = torch.softmax(self.layer_logits, dim=0)
            return self.net((x.float() * w[None, :, None]).sum(dim=1))

    return LayerWeightedHead()


def _mlp_head(dim: int, hidden: int = 256, dropout: float = 0.2) -> Any:
    nn = _torch().nn
    return nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, hidden), nn.ReLU(), nn.Dropout(dropout),
                         nn.Linear(hidden, len(AFFECT)))


def trainable_parameters(model: Any) -> int:
    return int(sum(p.numel() for p in model.parameters() if p.requires_grad))


# --- runners ----------------------------------------------------------------------------------------


def _labels_tensor(rows: Sequence[Mapping[str, Any]]) -> Any:
    torch = _torch()
    return torch.tensor([AFFECT.index(r["affect"]) for r in rows], dtype=torch.long)


def _cached(corpus: Path, name: str, rows: Sequence[Mapping[str, Any]]) -> Any:
    np = importlib.import_module("numpy")
    torch = _torch()
    index = json.loads((corpus / name / "index.json").read_text(encoding="utf-8"))
    emb = np.load(corpus / name / "embeddings.npy")
    pos = {cid: i for i, cid in enumerate(index["clip_ids"])}
    missing = [r["clip_id"] for r in rows if r["clip_id"] not in pos]
    if missing:
        raise TrainError(f"{len(missing)} usable clips are missing from the {name} cache; rerun preprocessing")
    return torch.from_numpy(emb[[pos[r["clip_id"]] for r in rows]].astype("float32"))


def run_head(kind: str, corpus: Path, rows: List[Dict[str, Any]], regime: str, seed: int, device: str,
             epochs: int) -> Dict[str, Any]:
    torch = _torch()
    torch.manual_seed(seed)
    sets = eval_sets(rows, regime)
    y = _labels_tensor(rows)
    evidence = sm.EVIDENCE_ACTED
    if kind == "baseline":
        train_ids = {rows[i]["clip_id"] for i in sets["train"]}
        results = {}
        for variant, per_speaker in (("speaker_normalised", True), ("pooled_normalised", False)):
            X = torch.tensor(sd.normalise(rows, per_speaker=per_speaker, train_ids=train_ids), dtype=torch.float32)
            model = torch.nn.Linear(X.shape[1], len(AFFECT))
            fit = fit_head(model, X, y, sets, sd.class_weights([rows[i]["affect"] for i in sets["train"]]),
                           epochs=epochs, lr=1e-2, wd=1e-2, batch=256, patience=30, seed=seed, device=device)
            preds = predict_labels(fit["model"], X, device)
            results[variant] = {"best_epoch": fit["best_epoch"], "trainable_parameters": trainable_parameters(model),
                                "scores": score_sets(rows, sets, preds, evidence), "_probs": predict_probs(fit["model"], X, device)}
        return {"variants": results}
    if kind == "whisper-head":
        X = _cached(corpus, "whisper_small", rows)
        model = _layer_weighted_head(X.shape[1], X.shape[2])
    elif kind == "e2v-head":
        X = _cached(corpus, "emotion2vec_plus_large", rows)
        model = _mlp_head(X.shape[1])
        evidence = sm.EVIDENCE_SEEN
    else:
        raise TrainError(f"unknown head {kind!r}")
    fit = fit_head(model, X, y, sets, sd.class_weights([rows[i]["affect"] for i in sets["train"]]),
                   epochs=epochs, lr=1e-3, wd=1e-3, batch=64, patience=10, seed=seed, device=device)
    probs = predict_probs(fit["model"], X, device)
    preds = [AFFECT[int(i)] for i in probs.argmax(dim=-1)]
    extra = {}
    if kind == "whisper-head":
        extra["layer_weights"] = [round(float(w), 4) for w in torch.softmax(fit["model"].layer_logits, 0)]
    return {"variants": {"default": {"best_epoch": fit["best_epoch"], "history": fit["history"],
                                     "trainable_parameters": trainable_parameters(fit["model"]),
                                     "scores": score_sets(rows, sets, preds, evidence), "_probs": probs,
                                     "_state": fit["model"].state_dict(), **extra}}}


def run_e2v_zeroshot(corpus: Path, rows: List[Dict[str, Any]], regime: str) -> Dict[str, Any]:
    np = importlib.import_module("numpy")
    index = json.loads((corpus / "emotion2vec_plus_large" / "index.json").read_text(encoding="utf-8"))
    scores = np.load(corpus / "emotion2vec_plus_large" / "scores.npy")
    pos = {cid: i for i, cid in enumerate(index["clip_ids"])}
    order = index["native_order"]
    sets = eval_sets(rows, regime)
    sets["train"] = []  # nothing is trained; score every non-train set
    forced, abstaining = [], []
    for r in rows:
        z = sm.e2v_zero_shot(scores[pos[r["clip_id"]]].tolist(), order, E2V_TO_AFFECT, AFFECT)
        forced.append(z["forced"])
        abstaining.append(z["abstaining"])
    all_sets = dict(sets)
    all_sets["all_train_split_too"] = sd.select(rows, "train", sd.TRAIN_REGIMES[regime])
    return {"variants": {
        "forced_5": {"trainable_parameters": 0, "scores": score_sets(rows, all_sets, forced, sm.EVIDENCE_SEEN)},
        "abstaining_9to5": {"trainable_parameters": 0,
                            "scores": score_sets(rows, all_sets, abstaining, sm.EVIDENCE_SEEN)},
    }}


# --- WavLM fine-tune ----------------------------------------------------------------------------------


def _read_clip(path: Path) -> Any:
    np = importlib.import_module("numpy")
    with wave.open(io.BytesIO(path.read_bytes())) as w:
        if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise TrainError("expected the trimmed 16 kHz mono clips from ml.ser.preprocess")
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").copy()


def _wavlm_model(directory: Path, freeze_layers: int) -> Any:
    torch = _torch()
    nn = torch.nn
    apply_offline_env()
    transformers = importlib.import_module("transformers")
    backbone = transformers.WavLMModel.from_pretrained(str(directory), local_files_only=True)
    backbone.freeze_feature_encoder()
    for p in backbone.feature_projection.parameters():
        p.requires_grad = False
    for layer in backbone.encoder.layers[:freeze_layers]:
        for p in layer.parameters():
            p.requires_grad = False
    n_states = backbone.config.num_hidden_layers + 1
    dim = backbone.config.hidden_size

    class WavLMSER(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = backbone
            self.layer_logits = nn.Parameter(torch.zeros(n_states))
            self.attn = nn.Sequential(nn.Linear(dim, 128), nn.Tanh(), nn.Linear(128, 1))
            self.head = nn.Sequential(nn.LayerNorm(2 * dim), nn.Linear(2 * dim, 256), nn.ReLU(), nn.Dropout(0.2),
                                      nn.Linear(256, len(AFFECT)))

        def forward(self, wav: Any, lengths: Any) -> Any:
            hidden = self.backbone(wav, output_hidden_states=True).hidden_states
            w = torch.softmax(self.layer_logits, dim=0)
            h = sum(w[i] * hidden[i] for i in range(len(hidden)))  # (B, T, D)
            frames = torch.clamp((lengths // 320), min=1, max=h.shape[1])
            mask = torch.arange(h.shape[1], device=h.device)[None, :] < frames[:, None]
            a = self.attn(h).squeeze(-1).masked_fill(~mask, -1e4)
            a = torch.softmax(a.float(), dim=1).to(h.dtype)[:, :, None]
            mean = (a * h).sum(dim=1)
            std = torch.sqrt(((a * (h - mean[:, None, :]) ** 2).sum(dim=1)).clamp(min=1e-6))
            return self.head(torch.cat([mean, std], dim=-1).float())

    return WavLMSER()


def _batch(clips: Sequence[Any], idx: Sequence[int], crop: Optional[int], rng: Any) -> Tuple[Any, Any]:
    np = importlib.import_module("numpy")
    torch = _torch()
    waves = []
    for i in idx:
        x = clips[i].astype(np.float32) / 32768.0
        if crop and x.size > crop:
            start = int(rng.integers(0, x.size - crop + 1))
            x = x[start:start + crop]
        x = (x - x.mean()) / (x.std() + 1e-7)  # per-utterance normalisation (WavLM preprocessing)
        waves.append(x)
    longest = max(w.size for w in waves)
    out = np.zeros((len(waves), longest), dtype=np.float32)
    for j, w in enumerate(waves):
        out[j, :w.size] = w
    return torch.from_numpy(out), torch.tensor([w.size for w in waves], dtype=torch.long)


def run_wavlm(corpus: Path, rows: List[Dict[str, Any]], regime: str, seed: int, models_root: Path, epochs: int,
              batch: int = 16, crop_s: float = 3.0, freeze_layers: int = 6) -> Dict[str, Any]:
    np = importlib.import_module("numpy")
    torch = _torch()
    if not torch.cuda.is_available():
        raise TrainError("WavLM fine-tuning needs the CUDA GPU")
    device = "cuda"
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    entry = ser_get(ser_manifest(), "wavlm_base_plus")
    directory = ser_model_dir(models_root, entry)
    if not rc.verify_files(directory, entry["files"], full_hash=False)["ok"]:
        raise TrainError("WavLM Base+ files are missing or the wrong size")
    sets = eval_sets(rows, regime)
    clips = [_read_clip(corpus / r["audio_rel"]) for r in rows]
    y = _labels_tensor(rows)
    model = _wavlm_model(directory, freeze_layers).to(device)
    backbone_params = [p for p in model.backbone.parameters() if p.requires_grad]
    head_params = [p for n, p in model.named_parameters() if p.requires_grad and not n.startswith("backbone.")]
    opt = torch.optim.AdamW([{"params": backbone_params, "lr": 3e-5}, {"params": head_params, "lr": 1e-3}],
                            weight_decay=1e-2)
    steps = epochs * math.ceil(len(sets["train"]) / batch)
    warm = max(1, steps // 10)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * max(0.0, (steps - s) / steps))
    weights = sd.class_weights([rows[i]["affect"] for i in sets["train"]])
    loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights, device=device))
    crop = int(crop_s * SAMPLE_RATE)
    torch.cuda.reset_peak_memory_stats()

    def infer(idx: Sequence[int]) -> Any:
        model.eval()
        out = []
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            for s in range(0, len(idx), batch):
                wav, lens = _batch(clips, idx[s:s + batch], None, rng)
                out.append(torch.softmax(model(wav.to(device), lens.to(device)).float(), -1).cpu())
        return torch.cat(out)

    best = {"uar": -1.0, "epoch": -1, "state": None}
    history = []
    started = time.perf_counter()
    for epoch in range(epochs):
        model.train()
        order = rng.permutation(sets["train"])
        total = 0.0
        t0 = time.perf_counter()
        for s in range(0, len(order), batch):
            idx = order[s:s + batch].tolist()
            wav, lens = _batch(clips, idx, crop, rng)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(wav.to(device), lens.to(device))
            loss = loss_fn(logits.float(), y[idx].to(device))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            opt.step()
            sched.step()
            total += loss.item() * len(idx)
        vprobs = infer(sets["val"])
        uar = sm.evaluate([rows[i]["affect"] for i in sets["val"]],
                          [AFFECT[int(k)] for k in vprobs.argmax(-1)], AFFECT)["uar"] or 0.0
        history.append({"epoch": epoch, "train_loss": round(total / len(order), 5), "val_uar": uar,
                        "epoch_seconds": round(time.perf_counter() - t0, 1)})
        print(json.dumps({"epoch": epoch, "val_uar": uar, "seconds": history[-1]["epoch_seconds"]}), flush=True)
        if uar > best["uar"]:
            best = {"uar": uar, "epoch": epoch,
                    "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()
                              if not k.startswith("backbone.") or _trainable(model, k)}}
    model.load_state_dict(best["state"], strict=False)
    probs = infer(list(range(len(rows))))
    preds = [AFFECT[int(i)] for i in probs.argmax(dim=-1)]
    return {"variants": {"default": {
        "best_epoch": best["epoch"], "history": history, "trainable_parameters": trainable_parameters(model),
        "frozen_backbone_layers": freeze_layers, "crop_seconds": crop_s, "batch": batch,
        "train_seconds": round(time.perf_counter() - started, 1),
        "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20, 1),
        "layer_weights": [round(float(w), 4) for w in torch.softmax(model.layer_logits.detach().float(), 0)],
        "scores": score_sets(rows, sets, preds, sm.EVIDENCE_ACTED), "_probs": probs, "_state": best["state"],
        "base_revision": entry["revision"]}}}


def _trainable(model: Any, key: str) -> bool:
    params = dict(model.named_parameters())
    return key in params and params[key].requires_grad


# --- output -------------------------------------------------------------------------------------------


def write_run(run_dir: Path, name: str, regime: str, seed: int, rows: Sequence[Mapping[str, Any]],
              result: Dict[str, Any], data_report: Mapping[str, Any]) -> Dict[str, Any]:
    torch = _torch()
    run_dir.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {"model": name, "regime": regime, "seed": seed, "version": TRAIN_VERSION,
                              "data": data_report, "variants": {}}
    for variant, res in result["variants"].items():
        probs = res.pop("_probs", None)
        state = res.pop("_state", None)
        report["variants"][variant] = res
        if probs is not None:
            lines = [json.dumps({"clip_id": r["clip_id"], "split": r["split"], "dataset": r["dataset"],
                                 "gold": r["affect"], "probs": [round(float(p), 5) for p in probs[i]]})
                     for i, r in enumerate(rows)]
            (run_dir / f"predictions-{variant}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if state is not None:
            torch.save(state, run_dir / f"weights-{variant}.pt")
    (run_dir / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return report


def headline(report: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for variant, res in report["variants"].items():
        row = {"model": report["model"], "variant": variant, "regime": report["regime"], "seed": report["seed"],
               "best_epoch": res.get("best_epoch"), "trainable_parameters": res.get("trainable_parameters")}
        for name, sc in res["scores"].items():
            row[f"{name}.uar"] = sc["uar"]
            row[f"{name}.min_class_recall"] = sc["min_class_recall"]
        row["evidence_class"] = next(iter(res["scores"].values()))["evidence_class"]
        out.append(row)
    return out


def compare(runs: Path) -> List[Dict[str, Any]]:
    rows = []
    for rep in sorted(runs.glob("*/report.json")):
        rows += headline(json.loads(rep.read_text(encoding="utf-8")))
    return sorted(rows, key=lambda r: (r["regime"], -(r.get("val.uar") or 0.0)))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.ser.train", description=__doc__.split("\n")[0])
    parser.add_argument("--training-root", default=None)
    parser.add_argument("--models-root", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, default_epochs in (("baseline", 300), ("whisper-head", 100), ("e2v-head", 100), ("wavlm", 8)):
        p = sub.add_parser(name)
        p.add_argument("--regime", choices=tuple(sd.TRAIN_REGIMES), default="both")
        p.add_argument("--seed", type=int, default=13)
        p.add_argument("--epochs", type=int, default=default_epochs)
    z = sub.add_parser("e2v-zeroshot")
    z.add_argument("--regime", choices=tuple(sd.TRAIN_REGIMES), default="both")
    sub.add_parser("compare")
    args = parser.parse_args(argv)

    from ..training import paths
    root = paths.training_root(args.training_root)
    corpus = paths.confined(root, *CORPUS_DIR)
    runs = paths.confined(root, *RUNS_DIR)
    if args.cmd == "compare":
        print(json.dumps(compare(runs), indent=1))
        return 0
    rows, data_report = sd.load_rows(corpus)
    torch = _torch()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    with network_blocked() as net:
        started = time.perf_counter()
        if args.cmd == "e2v-zeroshot":
            result, seed = run_e2v_zeroshot(corpus, rows, args.regime), 0
        elif args.cmd == "wavlm":
            result, seed = run_wavlm(corpus, rows, args.regime, args.seed, rc.models_root(args.models_root),
                                     args.epochs), args.seed
        else:
            result, seed = run_head(args.cmd, corpus, rows, args.regime, args.seed, device, args.epochs), args.seed
        report = write_run(runs / f"{args.cmd}-{args.regime}-s{seed}", args.cmd, args.regime, seed, rows, result,
                           {**data_report, "device": device, "seconds": round(time.perf_counter() - started, 1)})
    report["network_attempts_blocked"] = net["attempts"]
    print(json.dumps({"network_attempts_blocked": net["attempts"], "headline": headline(report)}, indent=1))
    return 0 if net["attempts"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
