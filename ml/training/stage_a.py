"""Stage A: domain-adaptive masked-language-model training of the pinned MuRIL checkpoint.

Schedule (documented, deterministic):
1. *Coverage pass*: one epoch over every training window marked ``coverage`` in the EXT-119
   corpus, so every usable record participates (the four smaller datasets with every window, the
   large suicide corpus with its first window per record), in a seeded shuffled order.
2. *Balanced continuation*: ``continuation_draws`` further windows drawn with dataset-aware
   temperature sampling (probability proportional to window count ** ``alpha``) over all training
   windows, so the large corpus cannot dominate while nothing is discarded.

Loss: dynamic 15% masking (80% [MASK], 10% random, 10% unchanged), cross-entropy at masked
positions only, each token weighted by its window's ``1 / duplicate-family size``. Validation uses
the held-out ``mlm_validation`` families with a fixed masking seed; perplexity is ``exp`` of the
mean masked-token loss. No causal or generative objective; nothing is ever decoded to text.
"""

import json
import math
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import paths, torchkit as tk

MASK_PROB = 0.15
MAX_LEN = 128


def load_corpus(root: Path) -> Dict[str, Any]:
    directory = paths.confined(root, *paths.EXTERNAL_CORPUS.split("/"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    segments = directory / "segments.jsonl"
    if paths.sha256_file(segments) != manifest["segments_sha256"]:
        raise RuntimeError("the EXT-119 corpus does not match its manifest hash")
    keep = ("uid", "dataset_id", "text", "weight", "mlm_partition", "coverage", "family")
    rows = [{k: s[k] for k in keep} for s in tk.read_jsonl(segments)]
    return {"manifest": manifest, "rows": rows}


def continuation_order(rows: Sequence[Mapping[str, Any]], draws: int, alpha: float, seed: int) -> Dict[str, Any]:
    pools: Dict[str, List[int]] = {}
    for i, r in enumerate(rows):
        pools.setdefault(r["dataset_id"], []).append(i)
    sources = sorted(pools)
    weights = [len(pools[s]) ** alpha for s in sources]
    rng = random.Random(f"{seed}|continuation")
    queues = {s: [] for s in sources}
    passes: Counter = Counter()
    order: List[int] = []
    for _ in range(draws):
        s = rng.choices(sources, weights)[0]
        if not queues[s]:
            queues[s] = list(pools[s])
            rng.shuffle(queues[s])
            passes[s] += 1
        order.append(queues[s].pop())
    drawn = Counter(rows[i]["dataset_id"] for i in order)
    total = sum(weights)
    return {"order": order, "drawn": dict(drawn), "passes_started": dict(passes),
            "share": {s: round(w / total, 4) for s, w in zip(sources, weights)}}


def mask_batch(tok: Any, texts: Sequence[str], generator: Any, device: str) -> Dict[str, Any]:
    t = tk.torch()
    enc = tok(list(texts), max_length=MAX_LEN, truncation=True, padding=True, return_tensors="pt")
    ids, attn = enc["input_ids"], enc["attention_mask"]
    special = t.zeros_like(ids, dtype=t.bool)
    for sid in {tok.cls_token_id, tok.sep_token_id, tok.pad_token_id}:
        special |= ids == sid
    candidates = attn.bool() & ~special
    prob = t.full(ids.shape, MASK_PROB) * candidates
    masked = t.bernoulli(prob, generator=generator).bool()
    for row in range(ids.shape[0]):  # at least one masked token per non-empty row
        if not masked[row].any() and candidates[row].any():
            pos = candidates[row].nonzero().flatten()
            masked[row, pos[t.randint(len(pos), (1,), generator=generator)]] = True
    labels = ids.clone()
    labels[~masked] = -100
    roll = t.rand(ids.shape, generator=generator)
    inputs = ids.clone()
    inputs[masked & (roll < 0.8)] = tok.mask_token_id
    rand_pos = masked & (roll >= 0.8) & (roll < 0.9)
    inputs[rand_pos] = t.randint(len(tok), ids.shape, generator=generator)[rand_pos]
    return {"input_ids": inputs.to(device), "attention_mask": attn.to(device), "labels": labels.to(device),
            "masked": masked.to(device)}


def masked_loss(model: Any, batch: Mapping[str, Any], weights: Optional[Any] = None) -> Any:
    t = tk.torch()
    hidden = model.bert(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]).last_hidden_state
    masked = batch["masked"]
    scores = model.cls(hidden[masked]).float()
    per_token = t.nn.functional.cross_entropy(scores, batch["labels"][masked], reduction="none")
    if weights is None:
        return per_token.mean()
    w = weights.unsqueeze(1).expand_as(masked)[masked]
    return (per_token * w).sum() / w.sum()


def evaluate(model: Any, tok: Any, rows: Sequence[Mapping[str, Any]], device: str, micro: int, seed: int) -> Dict:
    t = tk.torch()
    model.eval()
    g = t.Generator().manual_seed(seed)
    total, tokens = 0.0, 0
    with t.inference_mode(), t.autocast(device_type="cuda", dtype=t.bfloat16, enabled=device == "cuda"):
        for batch_rows in tk.chunks(list(rows), micro):
            b = mask_batch(tok, [r["text"] for r in batch_rows], g, device)
            n = int(b["masked"].sum())
            total += float(masked_loss(model, b)) * n
            tokens += n
    model.train()
    mean = total / max(tokens, 1)
    return {"masked_tokens": tokens, "loss": round(mean, 4), "perplexity": round(math.exp(mean), 3)}


def run(root: Path, models_root: Optional[str] = None, *, micro: int = 32, accum: int = 1, lr: float = 5e-5,
        seed: int = 20260912, continuation_draws: int = 40000, alpha: float = 0.3, limit: Optional[int] = None,
        log: Any = print) -> Dict[str, Any]:
    t, tf = tk.torch(), tk.transformers()
    tk.seed_everything(seed)
    device = tk.device()
    base = tk.base_model_dir(models_root)
    corpus = load_corpus(root)
    rows = corpus["rows"]
    train = [r for r in rows if r["mlm_partition"] == "train"]
    coverage = sorted((r for r in train if r["coverage"]), key=lambda r: r["uid"])
    random.Random(f"{seed}|coverage").shuffle(coverage)
    val = sorted((r for r in rows if r["mlm_partition"] == "mlm_validation"), key=lambda r: r["uid"])
    cont = continuation_order(train, continuation_draws, alpha, seed)
    cont_rows = [train[i] for i in cont["order"]]
    if limit:  # smoke runs only
        coverage, cont_rows, val = coverage[:limit], cont_rows[:max(1, limit // 4)], val[:max(1, limit // 4)]

    tok = tk.load_tokenizer(base["dir"])
    model = tf.BertForMaskedLM.from_pretrained(str(base["dir"]), local_files_only=True).to(device)
    model.train()
    decay = [p for n, p in model.named_parameters() if p.requires_grad and not any(k in n for k in ("bias", "LayerNorm"))]
    no_decay = [p for n, p in model.named_parameters() if p.requires_grad and any(k in n for k in ("bias", "LayerNorm"))]
    opt = t.optim.AdamW([{"params": decay, "weight_decay": 0.01}, {"params": no_decay, "weight_decay": 0.0}],
                        lr=lr, fused=device == "cuda")
    steps = math.ceil(len(coverage) / (micro * accum)) + math.ceil(len(cont_rows) / (micro * accum))
    sched = tf.get_linear_schedule_with_warmup(opt, max(1, int(0.06 * steps)), steps)
    monitor = tk.Monitor()
    gen = t.Generator().manual_seed(seed)
    run_id = time.strftime("run-%Y%m%d-%H%M%S")
    out = paths.confined(root, "checkpoints", "stage-a", run_id)
    out.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "stage": "A", "objective": "masked_language_model", "run_id": run_id, "seed": seed,
        "base": {"repo": base["repo"], "revision": base["revision"]},
        "corpus": {"name": corpus["manifest"]["corpus"], "segments_sha256": corpus["manifest"]["segments_sha256"]},
        "config": {"micro_batch": micro, "grad_accumulation": accum, "lr": lr, "weight_decay": 0.01,
                   "warmup_fraction": 0.06, "schedule": "linear", "max_len": MAX_LEN, "mask_prob": MASK_PROB,
                   "precision": "bf16 autocast, fp32 master weights" if device == "cuda" else "fp32",
                   "grad_clip": 1.0, "optimizer": "AdamW (fused)", "alpha": alpha,
                   "continuation_draws": len(cont_rows), "limit": limit},
        "coverage": {"windows": len(coverage), "by_dataset": dict(Counter(r["dataset_id"] for r in coverage))},
        "continuation": {k: cont[k] for k in ("drawn", "passes_started", "share")},
        "validation_windows": len(val), "device": device, "packages": tk.package_versions(),
    }
    report["validation_before"] = evaluate(model, tok, val, device, micro, seed)
    log(f"stage A: {len(coverage)} coverage + {len(cont_rows)} continuation windows, {steps} optimiser steps; "
        f"validation perplexity before {report['validation_before']['perplexity']}")

    def phase(name: str, phase_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        running, seen, started = 0.0, 0, time.perf_counter()
        batches = list(tk.chunks(list(phase_rows), micro))
        for i, batch_rows in enumerate(batches):
            b = mask_batch(tok, [r["text"] for r in batch_rows], gen, device)
            w = t.tensor([float(r["weight"]) for r in batch_rows], device=device)
            with t.autocast(device_type="cuda", dtype=t.bfloat16, enabled=device == "cuda"):
                loss = masked_loss(model, b, w) / accum
            loss.backward()
            if (i + 1) % accum == 0 or i + 1 == len(batches):
                t.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
                opt.zero_grad(set_to_none=True)
            running += float(loss.detach()) * accum
            seen += 1
            if (i + 1) % 500 == 0 or i + 1 == len(batches):
                monitor.sample()
                rate = (i + 1) * micro / (time.perf_counter() - started)
                log(f"  {name}: batch {i + 1}/{len(batches)} loss {running / seen:.4f} "
                    f"lr {sched.get_last_lr()[0]:.2e} {rate:.0f} windows/s temp {monitor.max_temp}")
                running, seen = 0.0, 0
        return {"batches": len(batches), "windows": len(phase_rows),
                "seconds": round(time.perf_counter() - started, 1)}

    try:
        report["coverage"]["result"] = phase("coverage", coverage)
        report["validation_after_coverage"] = evaluate(model, tok, val, device, micro, seed)
        tk.save_pretrained_atomic(model, tok, out / "coverage", {"stage": "A", "phase": "coverage", **report["base"]})
        report["continuation"]["result"] = phase("continuation", cont_rows)
        report["validation_after_continuation"] = evaluate(model, tok, val, device, micro, seed)
    except t.cuda.OutOfMemoryError:
        report["status"] = "out_of_memory"
        report["resources"] = monitor.report()
        paths.write_json(out / "report.json", report)
        raise
    hashes = tk.save_pretrained_atomic(model, tok, out / "final", {"stage": "A", "phase": "final", **report["base"],
                                                                     "seed": seed, "run_id": run_id})
    state = out / "training_state.pt.partial"
    t.save({"optimizer": opt.state_dict(), "scheduler": sched.state_dict(), "steps": steps, "seed": seed}, state)
    state.replace(out / "training_state.pt")
    report.update({"status": "completed", "optimizer_steps": steps, "final_files_sha256": hashes,
                   "resources": monitor.report(), "checkpoint": paths.label(out / "final", root)})
    paths.write_json(out / "report.json", report)
    paths.write_json(paths.confined(root, "checkpoints", "stage-a", "SELECTED.json"),
                     {"run_id": run_id, "checkpoint": f"checkpoints/stage-a/{run_id}/final"})
    return report
