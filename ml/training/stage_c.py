"""Stage C: the SAHAY multi-label shadow head, trained on private fictional records only.

Encoder: the Stage A domain-adapted MuRIL (predeclared; Stage B auxiliary heads never initialise
or touch this model, so no source label can shape the SAHAY head). Head: one independent logit per
schema detector category, BCE-with-logits, fixed uncalibrated 0.5 reporting threshold.

Per seed: train up to ``epochs`` with early stopping (patience ``patience``) on the fictional
*validation* split only. Selection, predeclared and applied both within a seed's epochs and
across seeds: (1) higher validation macro F1, (2) higher minimum per-label recall, (3) lower
validation loss, (4) lower seed / earlier epoch. The ``synthetic_development_test`` split is
scored once per seed after its checkpoint is fixed, and never influences any choice. No SAHAY
dev, candidate, red-team, locked or blind record is read here.
"""

import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..shadow import model as sm
from . import fictional, metrics, paths, torchkit as tk

EPOCHS = 6
PATIENCE = 2


def encoder_dir(root: Path) -> Tuple[Path, str]:
    pointer = json.loads(paths.confined(root, "checkpoints", "stage-a", "SELECTED.json").read_text(encoding="utf-8"))
    return paths.confined(root, *pointer["checkpoint"].split("/")), pointer["run_id"]


def _data(records: Sequence[Mapping[str, Any]], split: str, limit: Optional[int]) -> List[Dict[str, Any]]:
    rows = [{"id": r["id"], "text": sm.model_text(r["turns"]), "labels": [float(r["labels"][n]) for n in sm.LABELS],
             "gold": dict(r["labels"]), "language": r["language"]} for r in records if r["split"] == split]
    rows.sort(key=lambda r: r["id"])
    return rows[:limit] if limit else rows


def predict(net: Any, tok: Any, rows: Sequence[Mapping[str, Any]], device: str, micro: int = 64
            ) -> Tuple[List[List[float]], float]:
    t = tk.torch()
    net.eval()
    probs: List[List[float]] = []
    total, n = 0.0, 0
    with t.inference_mode(), t.autocast(device_type="cuda", dtype=t.bfloat16, enabled=device == "cuda"):
        for batch in tk.chunks(list(rows), micro):
            enc = tok([r["text"] for r in batch], max_length=sm.MAX_LEN, truncation=True, padding=True,
                      return_tensors="pt").to(device)
            logits = net(enc["input_ids"], enc["attention_mask"]).float()
            y = t.tensor([r["labels"] for r in batch], device=device)
            total += float(t.nn.functional.binary_cross_entropy_with_logits(logits, y, reduction="sum"))
            n += y.numel()
            probs += t.sigmoid(logits).cpu().tolist()
    return probs, total / max(n, 1)


def score(rows: Sequence[Mapping[str, Any]], probs: Sequence[Sequence[float]]) -> Dict[str, Any]:
    gold = [r["gold"] for r in rows]
    pred = [metrics.firings(p, sm.LABELS) for p in probs]
    out = metrics.summary(gold, pred, sm.LABELS)
    out["by_language"] = metrics.by_group(gold, pred, [r["language"] for r in rows], sm.LABELS)
    return out


def train_seed(root: Path, seed: int, records: Sequence[Mapping[str, Any]], enc_dir: Path, *, micro: int = 32,
               lr: float = 3e-5, head_lr: float = 1e-3, epochs: int = EPOCHS, patience: int = PATIENCE,
               limit: Optional[int] = None, log: Any = print, tag: str = "run1") -> Dict[str, Any]:
    t, tf = tk.torch(), tk.transformers()
    tk.seed_everything(seed)
    device = tk.device()
    train, val, test = (_data(records, s, limit) for s in fictional.SPLITS)
    tok = tk.load_tokenizer(enc_dir)
    net = sm.build_network(sm.load_encoder(enc_dir)).to(device)
    opt = t.optim.AdamW([{"params": net.encoder.parameters(), "lr": lr},
                         {"params": list(net.head.parameters()), "lr": head_lr}], weight_decay=0.01,
                        fused=device == "cuda")
    steps = epochs * ((len(train) + micro - 1) // micro)
    sched = tf.get_linear_schedule_with_warmup(opt, max(1, int(0.06 * steps)), steps)
    monitor = tk.Monitor()
    history, best, best_state, stale = [], None, None, 0
    for epoch in range(1, epochs + 1):
        net.train()
        order = list(train)
        random.Random(f"{seed}|epoch{epoch}").shuffle(order)
        running = 0.0
        for batch in tk.chunks(order, micro):
            enc = tok([r["text"] for r in batch], max_length=sm.MAX_LEN, truncation=True, padding=True,
                      return_tensors="pt").to(device)
            y = t.tensor([r["labels"] for r in batch], device=device)
            with t.autocast(device_type="cuda", dtype=t.bfloat16, enabled=device == "cuda"):
                logits = net(enc["input_ids"], enc["attention_mask"])
            loss = t.nn.functional.binary_cross_entropy_with_logits(logits.float(), y)
            loss.backward()
            t.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            running += float(loss.detach())
        monitor.sample()
        probs, val_loss = predict(net, tok, val, device)
        val_scores = score(val, probs)
        entry = {"epoch": epoch, "train_loss": round(running / max(1, (len(order) + micro - 1) // micro), 4),
                 "validation_loss": round(val_loss, 5), "validation_macro_f1": val_scores["macro"]["f1"],
                 "validation_min_label_recall": val_scores["min_label_recall"]}
        history.append(entry)
        log(f"  seed {seed} epoch {epoch}: train loss {entry['train_loss']} val loss {entry['validation_loss']} "
            f"val macro F1 {entry['validation_macro_f1']} min recall {entry['validation_min_label_recall']}")
        candidate = {"seed": seed, "epoch": epoch, "validation": val_scores, "validation_loss": val_loss}
        if best is None or metrics.selection_key(candidate) < metrics.selection_key(best):
            best, stale = candidate, 0
            best_state = {part: {k: v.detach().to("cpu", copy=True) for k, v in module.state_dict().items()}
                          for part, module in (("encoder", net.encoder), ("head", net.head))}
        else:
            stale += 1
            if stale >= patience:
                log(f"  seed {seed}: early stop after epoch {epoch}")
                break
    net.encoder.load_state_dict(best_state["encoder"])
    net.head.load_state_dict(best_state["head"])
    test_probs, test_loss = predict(net, tok, test, device)
    repeat, _ = predict(net, tok, test, device)
    target = paths.confined(root, "checkpoints", "stage-c", f"{tag}-seed-{seed}")
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        tk._remove_tree(partial)
    sm.save(net, tok, partial, {"seed": seed, "epoch": best["epoch"], "stage": "C"})
    hashes = {p.relative_to(partial).as_posix(): paths.sha256_file(p) for p in sorted(partial.rglob("*"))
              if p.is_file()}
    if target.exists():
        tk._remove_tree(target)
    partial.replace(target)
    result = {"seed": seed, "selected_epoch": best["epoch"], "history": history,
              "validation": best["validation"], "validation_loss": round(best["validation_loss"], 5),
              "synthetic_development_test": score(test, test_probs),
              "synthetic_development_test_loss": round(test_loss, 5),
              "deterministic_repeat_identical": repeat == test_probs,
              "records": {"train": len(train), "validation": len(val), "synthetic_development_test": len(test)},
              "config": {"micro_batch": micro, "encoder_lr": lr, "head_lr": head_lr, "epochs_max": epochs,
                         "patience": patience, "loss": "BCEWithLogits", "threshold": metrics.THRESHOLD,
                         "precision": "bf16 autocast" if device == "cuda" else "fp32", "grad_clip": 1.0,
                         "optimizer": "AdamW (fused)", "schedule": "linear, 6% warmup", "limit": limit},
              "checkpoint": paths.label(target, root), "files_sha256": hashes, "resources": monitor.report()}
    del net, opt
    t.cuda.empty_cache()
    return result


SELECTION_RULE = ["higher validation macro F1", "higher minimum per-label validation recall", "lower validation loss",
                  "lower numeric seed", "earlier run"]


def run(root: Path, seeds: Sequence[int] = (13, 42, 97), limit: Optional[int] = None, log: Any = print, *,
        epochs: int = EPOCHS, patience: int = PATIENCE, tag: str = "run1") -> Dict[str, Any]:
    if not tag.isalnum():
        raise ValueError("tag must be alphanumeric")
    started = time.perf_counter()
    enc_dir, stage_a_run = encoder_dir(root)
    records = fictional.load(root)
    corpus = json.loads(paths.confined(root, *paths.FICTIONAL_CORPUS.split("/"), "manifest.json")
                        .read_text(encoding="utf-8"))
    results = [dict(train_seed(root, s, records, enc_dir, epochs=epochs, patience=patience, limit=limit, log=log,
                               tag=tag), run=tag) for s in sorted(seeds)]
    report = {"stage": "C", "run": tag, "model_id": sm.MODEL_ID, "labels": list(sm.LABELS),
              "stage_a_run": stage_a_run, "fictional_corpus_sha256": corpus["records_sha256"], "seeds": results,
              "config": {"epochs_max": epochs, "patience": patience}, "packages": tk.package_versions(),
              "seconds": round(time.perf_counter() - started, 1),
              "evidence_class": "synthetic development evidence (fictional; not independent, blind, locked or official)"}
    paths.write_json(paths.confined(root, "reports", "stage-c", f"{tag}.json"), report)
    report["selection"] = select_all(root)
    return report


def select_all(root: Path) -> Dict[str, Any]:
    """Apply the predeclared rule (validation only) to every seed result of every Stage C run."""
    candidates = []
    for path in sorted(paths.confined(root, "reports", "stage-c").glob("run*.json")):
        for result in json.loads(path.read_text(encoding="utf-8"))["seeds"]:
            candidates.append(result)
    ranked = sorted(candidates, key=lambda r: (*metrics.selection_key(r), r["run"]))
    chosen = ranked[0]
    selection = {"rule": SELECTION_RULE, "candidates": [
        {"run": r["run"], "seed": r["seed"], "epoch": r["selected_epoch"],
         "validation_macro_f1": r["validation"]["macro"]["f1"],
         "validation_min_label_recall": r["validation"]["min_label_recall"],
         "validation_loss": r["validation_loss"]} for r in ranked],
        "selected": {"run": chosen["run"], "seed": chosen["seed"], "epoch": chosen["selected_epoch"]},
        "note": "chosen on the fictional validation split only; synthetic_development_test and every exposed "
                "SAHAY corpus played no part"}
    paths.write_json(paths.confined(root, "reports", "stage-c", "selection.json"), selection)
    paths.write_json(paths.confined(root, "checkpoints", "stage-c", "SELECTED.json"),
                     {"run": chosen["run"], "seed": chosen["seed"],
                      "checkpoint": f"checkpoints/stage-c/{chosen['run']}-seed-{chosen['seed']}",
                      "model_id": sm.MODEL_ID, "rule": SELECTION_RULE})
    return selection
