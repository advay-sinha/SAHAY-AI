"""Text-affect training and evaluation (plan M12f, run R6). Private model environment only.

    python -m ml.textaffect.train muril-stagea   [--seed N] [--epochs N]   # Stage A domain-adapted MuRIL
    python -m ml.textaffect.train muril-base     [--seed N]                # pinned base MuRIL (ablation)
    python -m ml.textaffect.train xlmr-base      [--seed N]                # pinned XLM-R base (challenger)
    python -m ml.textaffect.train compare

Protocol:
  * training uses the ``train`` split of every language present (hi, hinglish, en);
  * the best epoch is chosen on pooled validation UAR only;
  * test is scored once, per language, plus the Hindi user turns alone;
  * the Hinglish rows are heuristic transliterations, so their scores are labelled
    ``transliterated_augmentation``; only human-written Hinglish can test real Hinglish;
  * everything is shadow output (D-9a). Nothing here feeds D4 or any product decision.

Runs are offline with network connections blocked, beneath
``<SAHAY_TRAINING_ROOT>/textaffect/runs/<encoder>-s<seed>/``. Predictions carry example ids
and probabilities only, never text.
"""

import argparse
import copy
import importlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..runtime import config as rc
from ..runtime.offline import apply_offline_env, network_blocked
from ..ser import data as sd
from ..ser import metrics as sm
from . import AFFECT_CLASSES

AFFECT = AFFECT_CLASSES
CORPUS_DIR = ("textaffect", "corpus-v1")
RUNS_DIR = ("textaffect", "runs")
TRAIN_VERSION = "textaffect-train-1.0"
MAX_LEN = 128
ENCODERS = ("muril-stagea", "muril-base", "xlmr-base")
EVIDENCE = {"hi": "source_corpus_dialogue_disjoint", "hinglish": "transliterated_augmentation",
            "en": "source_corpus_upstream_split"}


class TextAffectError(Exception):
    """A refusal with a fixed message: no path, no text."""


def _torch() -> Any:
    return importlib.import_module("torch")


# --- data ------------------------------------------------------------------------------------------


def load_examples(corpus: Path) -> List[Dict[str, Any]]:
    path = corpus / "examples.jsonl"
    if not path.is_file():
        raise TextAffectError("examples.jsonl is missing; run `python -m ml.data.affect_corpus build` first")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in rows:
        r["affect"] = r["label"].split(":", 1)[1]
        if r["affect"] not in AFFECT:
            raise TextAffectError("a label outside the affect classes reached training")
    return rows


def eval_sets(rows: Sequence[Mapping[str, Any]]) -> Dict[str, List[int]]:
    sets: Dict[str, List[int]] = {"train": [i for i, r in enumerate(rows) if r["split"] == "train"],
                                  "val": [i for i, r in enumerate(rows) if r["split"] == "val"]}
    for lang in sorted({r["language"] for r in rows}):
        sets[f"test:{lang}"] = [i for i, r in enumerate(rows) if r["split"] == "test" and r["language"] == lang]
    sets["test:hi_user_turns"] = [i for i, r in enumerate(rows) if r["split"] == "test" and r["language"] == "hi"
                                  and r.get("speaker") == "user"]
    if not sets["train"] or not sets["val"]:
        raise TextAffectError("the training or validation split is empty")
    return {k: v for k, v in sets.items() if v}


def score_sets(rows: Sequence[Mapping[str, Any]], sets: Mapping[str, List[int]],
               preds: Sequence[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, idx in sets.items():
        if name == "train":
            continue
        lang = name.split(":", 1)[1].split("_")[0] if ":" in name else "pooled"
        res = sm.evaluate([rows[i]["affect"] for i in idx], [preds[i] for i in idx], AFFECT,
                          EVIDENCE.get(lang, "pooled_validation"))
        out[name] = res
    return out


# --- encoders ------------------------------------------------------------------------------------


def encoder_dir(name: str, training_root: Path, models_root: Optional[str]) -> Tuple[Path, str]:
    if name == "muril-stagea":
        from ..training.stage_c import encoder_dir as stage_a_dir
        directory, run_id = stage_a_dir(training_root)
        return directory, f"stage-a:{run_id}"
    manifest = rc.load_manifest()
    entry = rc.get_model(manifest, "muril_base_cased" if name == "muril-base" else "xlm_roberta_base")
    directory = rc.model_dir(rc.models_root(models_root), entry)
    if not rc.verify_files(directory, entry["files"], full_hash=False)["ok"]:
        raise TextAffectError(f"the pinned {entry['logical_id']} files are missing or the wrong size")
    return directory, f"{entry['logical_id']}@{entry['revision']}"


def build_model(directory: Path) -> Tuple[Any, Any]:
    torch = _torch()
    nn = torch.nn
    apply_offline_env()
    transformers = importlib.import_module("transformers")
    tokenizer = transformers.AutoTokenizer.from_pretrained(str(directory), local_files_only=True)
    encoder = transformers.AutoModel.from_pretrained(str(directory), local_files_only=True, add_pooling_layer=False)

    class AffectClassifier(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoder = encoder
            self.dropout = nn.Dropout(0.1)
            self.head = nn.Linear(encoder.config.hidden_size, len(AFFECT))

        def forward(self, input_ids: Any, attention_mask: Any) -> Any:
            h = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            m = attention_mask.unsqueeze(-1).to(h.dtype)
            pooled = (h * m).sum(dim=1) / m.sum(dim=1).clamp(min=1.0)
            return self.head(self.dropout(pooled).float())

    return AffectClassifier(), tokenizer


def _batches(tokenizer: Any, texts: Sequence[str], idx: Sequence[int], batch: int) -> Any:
    for s in range(0, len(idx), batch):
        chunk = list(idx[s:s + batch])
        enc = tokenizer([texts[i] for i in chunk], padding=True, truncation=True, max_length=MAX_LEN,
                        return_tensors="pt")
        yield chunk, enc


def predict(model: Any, tokenizer: Any, texts: Sequence[str], idx: Sequence[int], device: str,
            batch: int = 128) -> Any:
    torch = _torch()
    model.eval()
    order = sorted(idx, key=lambda i: len(texts[i]))  # length-sorted for speed; results re-ordered
    probs: Dict[int, Any] = {}
    with torch.inference_mode(), torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda"):
        for chunk, enc in _batches(tokenizer, texts, order, batch):
            logits = model(enc["input_ids"].to(device), enc["attention_mask"].to(device))
            for i, p in zip(chunk, torch.softmax(logits.float(), -1).cpu()):
                probs[i] = p
    return torch.stack([probs[i] for i in idx])


def run(name: str, corpus: Path, training_root: Path, models_root: Optional[str], seed: int, epochs: int,
        batch: int = 32, lr: float = 2e-5) -> Dict[str, Any]:
    torch = _torch()
    from ..training import torchkit as tk
    tk.seed_everything(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    rows = load_examples(corpus)
    sets = eval_sets(rows)
    texts = [r["text"] for r in rows]
    y = torch.tensor([AFFECT.index(r["affect"]) for r in rows], dtype=torch.long)
    directory, provenance = encoder_dir(name, training_root, models_root)
    model, tokenizer = build_model(directory)
    model = model.to(device)
    head = [p for n, p in model.named_parameters() if n.startswith("head.")]
    body = [p for n, p in model.named_parameters() if not n.startswith("head.")]
    opt = torch.optim.AdamW([{"params": body, "lr": lr}, {"params": head, "lr": 1e-3}], weight_decay=0.01)
    steps = epochs * math.ceil(len(sets["train"]) / batch)
    warm = max(1, int(0.06 * steps))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * max(0.0, (steps - s) / steps))
    weights = sd.class_weights([rows[i]["affect"] for i in sets["train"]], AFFECT)
    loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights, device=device))
    gen = torch.Generator().manual_seed(seed)
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    best: Dict[str, Any] = {"uar": -1.0, "epoch": -1, "state": None}
    history = []
    started = time.perf_counter()
    for epoch in range(epochs):
        model.train()
        order = [sets["train"][int(k)] for k in torch.randperm(len(sets["train"]), generator=gen)]
        total, t0 = 0.0, time.perf_counter()
        for chunk, enc in _batches(tokenizer, texts, order, batch):
            with torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda"):
                logits = model(enc["input_ids"].to(device), enc["attention_mask"].to(device))
            loss = loss_fn(logits.float(), y[chunk].to(device))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            total += loss.item() * len(chunk)
        vprobs = predict(model, tokenizer, texts, sets["val"], device)
        uar = sm.evaluate([rows[i]["affect"] for i in sets["val"]], [AFFECT[int(k)] for k in vprobs.argmax(-1)],
                          AFFECT)["uar"] or 0.0
        history.append({"epoch": epoch, "train_loss": round(total / len(order), 5), "val_uar": uar,
                        "epoch_seconds": round(time.perf_counter() - t0, 1)})
        print(json.dumps({"epoch": epoch, "val_uar": uar, "seconds": history[-1]["epoch_seconds"]}), flush=True)
        if uar > best["uar"]:
            best = {"uar": uar, "epoch": epoch,
                    "state": {k: v.detach().to("cpu", copy=True) for k, v in model.state_dict().items()}}
    model.load_state_dict(best["state"])
    scored = sorted({i for k, v in sets.items() if k != "train" for i in v})
    probs = predict(model, tokenizer, texts, scored, device)
    full = {i: p for i, p in zip(scored, probs)}
    preds = [AFFECT[int(full[i].argmax())] if i in full else "neutral" for i in range(len(rows))]
    report = {
        "encoder": name, "provenance": provenance, "seed": seed, "version": TRAIN_VERSION,
        "best_epoch": best["epoch"], "history": history, "class_weights": weights,
        "train_rows": len(sets["train"]), "languages": sorted({r["language"] for r in rows}),
        "trainable_parameters": int(sum(p.numel() for p in model.parameters() if p.requires_grad)),
        "train_seconds": round(time.perf_counter() - started, 1), "device": device,
        "scores": score_sets(rows, sets, preds), "status": "shadow_only_D-9a",
    }
    if device == "cuda":
        report["peak_vram_mib"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
    return {"report": report, "state": best["state"], "rows": rows, "probs": full}


def write_run(run_dir: Path, result: Mapping[str, Any]) -> None:
    torch = _torch()
    run_dir.mkdir(parents=True, exist_ok=True)
    rows, probs = result["rows"], result["probs"]
    lines = [json.dumps({"id": rows[i]["id"], "split": rows[i]["split"], "language": rows[i]["language"],
                         "gold": rows[i]["affect"], "probs": [round(float(x), 5) for x in p]})
             for i, p in sorted(probs.items())]
    (run_dir / "predictions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    torch.save(result["state"], run_dir / "weights.pt")
    (run_dir / "report.json").write_text(json.dumps(result["report"], indent=1, sort_keys=True) + "\n",
                                         encoding="utf-8")


def headline(report: Mapping[str, Any]) -> Dict[str, Any]:
    row = {"encoder": report["encoder"], "seed": report["seed"], "best_epoch": report["best_epoch"]}
    for name, sc in report["scores"].items():
        row[f"{name}.uar"] = sc["uar"]
        row[f"{name}.macro_f1"] = sc["macro_f1"]
    return row


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.textaffect.train", description=__doc__.split("\n")[0])
    parser.add_argument("--training-root", default=None)
    parser.add_argument("--models-root", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ENCODERS:
        p = sub.add_parser(name)
        p.add_argument("--seed", type=int, default=13)
        p.add_argument("--epochs", type=int, default=3)
        p.add_argument("--batch", type=int, default=32)
    sub.add_parser("compare")
    args = parser.parse_args(argv)
    from ..training import paths
    root = paths.training_root(args.training_root)
    runs = paths.confined(root, *RUNS_DIR)
    if args.cmd == "compare":
        rows = [headline(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(runs.glob("*/report.json"))]
        print(json.dumps(sorted(rows, key=lambda r: -(r.get("val.uar") or 0.0)), indent=1))
        return 0
    corpus = paths.confined(root, *CORPUS_DIR)
    with network_blocked() as net:
        result = run(args.cmd, corpus, root, args.models_root, args.seed, args.epochs, args.batch)
        write_run(runs / f"{args.cmd}-s{args.seed}", result)
    print(json.dumps({"network_attempts_blocked": net["attempts"], "headline": headline(result["report"])}, indent=1))
    return 0 if net["attempts"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
