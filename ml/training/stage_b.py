"""Stage B: source-specific auxiliary heads, as isolated diagnostics.

One head per source whose label meaning is documented (the EXT-119 corpus marks them with
``aux_task``); the opaque sentiment classes get none. Every head keeps its ``source:<dataset>:``
label space; a window's loss touches only its own source's head (labels of other sources are
masked out); there is no shared risk target and no SAHAY, routing, SVI, D4 or diagnosis output.

The run starts from the Stage A encoder and saves its own isolated checkpoint. It is never the
Stage C initialisation and never loaded by the shadow runtime or the demonstration, so source
labels cannot reach SAHAY output. Metrics are source-namespace metrics on the corpus's
family-isolated auxiliary ``test`` bucket, never SAHAY safety metrics.
"""

import importlib
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import metrics, paths, torchkit as tk
from .stage_c import encoder_dir

PER_SOURCE_TRAIN_CAP = 12000
PER_SOURCE_TEST_CAP = 3000


def tasks(root: Path) -> Dict[str, Any]:
    directory = paths.confined(root, *paths.EXTERNAL_CORPUS.split("/"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    by_source: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: {"train": [], "test": []})
    vocab: Dict[str, set] = defaultdict(set)
    kind: Dict[str, str] = {}
    for s in tk.read_jsonl(directory / "segments.jsonl"):
        if not s.get("aux_task") or s.get("opaque_labels") or not s["source_labels"]:
            continue
        src = s["dataset_id"]
        prefix = f"source:{src}:"
        if not all(lab.startswith(prefix) for lab in s["source_labels"]):
            raise RuntimeError("a label outside its source namespace reached Stage B")
        kind[src] = s["aux_task"]
        vocab[src].update(s["source_labels"])
        by_source[src][s["aux_split"]].append({"uid": s["uid"], "text": s["text"], "labels": s["source_labels"],
                                               "weight": s["weight"]})
    return {"manifest": manifest, "data": by_source, "vocab": {k: sorted(v) for k, v in vocab.items()}, "kind": kind}


def _sample(rows: List[Dict[str, Any]], cap: int, salt: str) -> List[Dict[str, Any]]:
    rows = sorted(rows, key=lambda r: r["uid"])
    random.Random(salt).shuffle(rows)
    return rows[:cap]


def run(root: Path, *, seed: int = 20260912, micro: int = 32, lr: float = 3e-5, head_lr: float = 1e-3,
        limit: Optional[int] = None, log: Any = print) -> Dict[str, Any]:
    t = tk.torch()
    tk.seed_everything(seed)
    device = tk.device()
    enc_dir, stage_a_run = encoder_dir(root)
    spec = tasks(root)
    sources = sorted(spec["vocab"])
    cap_train = limit or PER_SOURCE_TRAIN_CAP
    cap_test = max(1, (limit or PER_SOURCE_TEST_CAP * 4) // 4)
    train = [dict(r, source=s) for s in sources for r in _sample(spec["data"][s]["train"], cap_train, f"{seed}|{s}")]
    test = {s: _sample(spec["data"][s]["test"], cap_test, f"{seed}|test|{s}") for s in sources}
    random.Random(f"{seed}|mix").shuffle(train)
    from ..shadow.model import load_encoder
    encoder = load_encoder(enc_dir).to(device)
    heads = t.nn.ModuleDict({s.replace(".", "_"): t.nn.Linear(encoder.config.hidden_size, len(spec["vocab"][s]))
                             for s in sources}).to(device)
    index = {s: {lab: i for i, lab in enumerate(spec["vocab"][s])} for s in sources}
    opt = t.optim.AdamW([{"params": encoder.parameters(), "lr": lr}, {"params": heads.parameters(), "lr": head_lr}],
                        weight_decay=0.01)
    tok = tk.load_tokenizer(enc_dir)
    monitor = tk.Monitor()
    started = time.perf_counter()

    def pooled(texts: Sequence[str]) -> Any:
        enc = tok(list(texts), max_length=128, truncation=True, padding=True, return_tensors="pt").to(device)
        hidden = encoder(**enc).last_hidden_state
        mask = enc["attention_mask"].unsqueeze(-1).to(hidden.dtype)
        return (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)

    encoder.train()
    for batch in tk.chunks(train, micro):
        with t.autocast(device_type="cuda", dtype=t.bfloat16, enabled=device == "cuda"):
            vecs = pooled([r["text"] for r in batch])
        loss, parts = 0.0, 0
        for s in sources:  # each window only reaches its own source head
            idx = [i for i, r in enumerate(batch) if r["source"] == s]
            if not idx:
                continue
            logits = heads[s.replace(".", "_")](vecs[idx].float())
            if spec["kind"][s] == "multi_label":
                y = t.zeros_like(logits)
                for row, i in enumerate(idx):
                    for lab in batch[i]["labels"]:
                        y[row, index[s][lab]] = 1.0
                loss = loss + t.nn.functional.binary_cross_entropy_with_logits(logits, y)
            else:
                y = t.tensor([index[s][batch[i]["labels"][0]] for i in idx], device=device)
                loss = loss + t.nn.functional.cross_entropy(logits, y)
            parts += 1
        (loss / max(parts, 1)).backward()
        t.nn.utils.clip_grad_norm_(list(encoder.parameters()) + list(heads.parameters()), 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
    monitor.sample()

    encoder.eval()
    results = {}
    with t.inference_mode():
        for s in sources:
            gold, pred = [], []
            for batch in tk.chunks(test[s], 64):
                with t.autocast(device_type="cuda", dtype=t.bfloat16, enabled=device == "cuda"):
                    logits = heads[s.replace(".", "_")](pooled([r["text"] for r in batch]).float())
                if spec["kind"][s] == "multi_label":
                    probs = t.sigmoid(logits).cpu().tolist()
                    for r, p in zip(batch, probs):
                        gold.append({lab: lab in r["labels"] for lab in spec["vocab"][s]})
                        pred.append(metrics.firings(p, spec["vocab"][s]))
                else:
                    choice = logits.argmax(dim=1).cpu().tolist()
                    for r, c in zip(batch, choice):
                        gold.append({lab: lab == r["labels"][0] for lab in spec["vocab"][s]})
                        pred.append({lab: i == c for i, lab in enumerate(spec["vocab"][s])})
            summary = metrics.summary(gold, pred, spec["vocab"][s])
            results[f"source:{s}"] = {"task": spec["kind"][s], "test_windows": len(gold),
                                      "train_windows": sum(r["source"] == s for r in train),
                                      "micro_f1": summary["micro"]["f1"], "macro_f1": summary["macro"]["f1"],
                                      "exact_match": summary["exact_match"],
                                      "per_label": {k: {m: v[m] for m in ("positives", "precision", "recall", "f1")}
                                                    for k, v in summary["per_label"].items()}}
    out = paths.confined(root, "checkpoints", "stage-b", "isolated")
    tk.save_pretrained_atomic(encoder, tok, out / "encoder", {"stage": "B", "isolated": True})
    st = importlib.import_module("safetensors.torch")
    st.save_file({k: v.detach().cpu().contiguous() for k, v in heads.state_dict().items()}, str(out / "aux_heads.safetensors"))
    report = {"stage": "B", "stage_a_run": stage_a_run, "isolated_from_stage_c": True, "sources": sources,
              "vocab_sizes": {s: len(v) for s, v in spec["vocab"].items()}, "train_windows": len(train),
              "train_by_source": dict(Counter(r["source"] for r in train)), "results": results,
              "caps": {"train_per_source": cap_train, "test_per_source": cap_test}, "seed": seed,
              "evidence_class": "external source-namespace auxiliary evidence; not a SAHAY safety metric",
              "seconds": round(time.perf_counter() - started, 1), "resources": monitor.report(),
              "checkpoint": paths.label(out, root)}
    paths.write_json(paths.confined(root, "reports", "stage-b", "report.json"), report)
    return report
