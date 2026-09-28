"""Stage W (plan M14, EXT-129): does weak supervision from source labels add anything? Shadow only.

    python -m ml.training.cli stage-w-plan          # record the predeclared plan (refuses later changes)
    python -m ml.training.cli stage-w --phase 1     # arms W0, W1, W2 at seed 13
    python -m ml.training.cli stage-w --phase 2     # seeds 42 and 97 of the arm chosen on validation
    python -m ml.training.cli stage-w-select
    python -m ml.training.cli stage-w-evaluate      # once, after selection (ml/training/stage_w_eval.py)
    python -m ml.training.cli stage-w --phase 1 --smoke 64   # tiny smoke run into stage-w-smoke/

The network is the Stage A MuRIL encoder, attention-masked mean pooling and one linear layer with
nine independent logits: the eight schema detector categories plus ``d5_text_distress``.
Predeclared arms:

- **W0:** the frozen Task 7B fictional train split only (8 labels). It reproduces Task 7B
  configuration C and is the baseline.
- **W1:** W0 plus the weak ``crisis_self_harm`` rows (subreddit of origin) and the weak ``D5`` rows
  (crowd-annotated stress), which train ``d5_text_distress``.
- **W2:** W1 plus the weak ``continuing_threat`` rows (a hate-speech label).

Weak data is keyed by its SAHAY training target, never by dataset name: only the governed builder
``ml/data/weak_corpus.py`` knows which dataset a target came from. A weak row supervises only its
one mapped logit; every other logit is masked out of its loss, so a forum post is never taught
"not coercion". Fictional rows supervise the eight detector logits,
with ``d5_text_distress`` masked (no fictional D5 labels). Each epoch uses every fictional train
row plus a weak draw of the same total size: each active source gets an equal share, capped at
its pool size with the remainder passed on, cycling through a seeded permutation so later epochs
see new windows.

Selection uses the fictional Task 7B validation split only, for epochs within a run and across
runs (the weak test buckets, the holdout and the exposed fixtures are never read here):
1. higher macro F1 over the eight detector labels;
2. higher minimum per-label recall;
3. lower validation loss (masked plain BCE);
4. lower seed, then the simpler arm (W0 before W1 before W2).

The threshold is a fixed, uncalibrated 0.5. Output is shadow only: it cannot change routing,
crisis handling, SVI, D5, D4, evidence, guardrails or anything victim-facing.
"""

import hashlib
import importlib
import json
import math
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..shadow import model as sm
from . import hardening as hx, metrics, paths, torchkit as tk
from .stage_c import encoder_dir
from .stage_c7b import rows as fictional_records

MODEL_ID = "experimental_weak_shadow_classifier"
D5_HEAD = "d5_text_distress"
LABELS: Tuple[str, ...] = tuple(sm.LABELS) + (D5_HEAD,)
DETECTOR_LABELS: Tuple[str, ...] = tuple(sm.LABELS)
TARGET_HEAD = {"crisis_self_harm": "crisis_self_harm", "continuing_threat": "continuing_threat", "D5": D5_HEAD}
WEAK_CORPUS = ("corpora", "weak-ext129-v1")
#: Arm -> the weak training targets it adds (keys of the weak pools).
ARMS: Dict[str, Tuple[str, ...]] = {
    "W0": (),
    "W1": ("D5", "crisis_self_harm"),
    "W2": ("D5", "continuing_threat", "crisis_self_harm"),
}
SCHEDULE = {"phase1": {"seeds": [13], "arms": ["W0", "W1", "W2"]}, "phase2": {"seeds": [42, 97], "arms": "winner"}}
HYPER = {"max_len": sm.MAX_LEN, "micro_batch": 16, "grad_accumulation": 2, "epochs_max": 20, "patience": 3,
         "encoder_lr": 3e-5, "head_lr": 1e-3, "weight_decay": 0.01, "warmup_fraction": 0.06, "grad_clip": 1.0,
         "loss": "masked focal", "gamma": 2.0, "threshold": metrics.THRESHOLD,
         "weak_budget": "equal to the fictional train size per epoch; equal shares, capped at pool size"}
SELECTION_RULE = ["higher validation macro F1 over the 8 detector labels", "higher minimum per-label validation recall",
                  "lower validation loss (masked plain BCE)", "lower numeric seed", "simpler arm (W0 < W1 < W2)"]
IDENTITY = ("experimental weak-supervision shadow output: development-only, uncalibrated, trained partly on source "
            "labels that are not SAHAY ground truth, not clinically validated, never authoritative")
ROOT = ("stage-w",)
SMOKE_ROOT = ("stage-w-smoke",)
HEAD_FILE = "head.safetensors"
CONFIG_FILE = "weak_shadow_config.json"
ENCODER_DIR = "encoder"


def _root(root: Path, *parts: str, smoke: bool = False) -> Path:
    return paths.confined(root, *(SMOKE_ROOT if smoke else ROOT), *parts)


# --- data ------------------------------------------------------------------------------------------------


def fictional_rows(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Task 7B records as 9-logit rows: eight supervised detector labels, D5 masked."""
    out = []
    for r in fictional_records(records):
        out.append({**r, "source": "fictional", "y": list(r["labels"]) + [0.0],
                    "m": [1.0] * len(DETECTOR_LABELS) + [0.0]})
    return out


def weak_row(r: Mapping[str, Any]) -> Dict[str, Any]:
    """One weak row: only its mapped logit is supervised."""
    head = TARGET_HEAD[r["target"]]
    i = LABELS.index(head)
    y = [0.0] * len(LABELS)
    m = [0.0] * len(LABELS)
    y[i], m[i] = float(r["value"]), 1.0
    return {"id": r["uid"], "text": r["text"], "source": r["target"], "language": r["language"], "y": y, "m": m,
            "head": head, "value": int(r["value"])}


def load_weak(root: Path, split: str) -> Dict[str, List[Dict[str, Any]]]:
    """Weak rows grouped by SAHAY training target (one source dataset per target in weak-ext129-v1)."""
    pools: Dict[str, List[Dict[str, Any]]] = {}
    for r in tk.read_jsonl(paths.confined(root, *WEAK_CORPUS, f"{split}.jsonl")):
        if r.get("evidence_class") != "weak_supervision_from_source_label":
            raise RuntimeError("a weak-corpus row without the weak-supervision evidence class")
        pools.setdefault(r["target"], []).append(weak_row(r))
    return {k: sorted(v, key=lambda x: x["id"]) for k, v in sorted(pools.items())}


def weak_manifest_sha(root: Path) -> Dict[str, str]:
    manifest = json.loads(paths.confined(root, *WEAK_CORPUS, "manifest.json").read_text(encoding="utf-8"))
    return dict(manifest["files_sha256"])


def quotas(pool_sizes: Mapping[str, int], budget: int) -> Dict[str, int]:
    """Equal shares of ``budget``, each capped at its pool size, remainder passed to larger pools."""
    out: Dict[str, int] = {}
    remaining = budget
    ordered = sorted(pool_sizes.items(), key=lambda kv: (kv[1], kv[0]))
    for i, (source, size) in enumerate(ordered):
        share = remaining // (len(ordered) - i)
        out[source] = min(size, share)
        remaining -= out[source]
    return dict(sorted(out.items()))


def weak_draw(pools: Mapping[str, Sequence[Mapping[str, Any]]], budget: int, seed: int, epoch: int
              ) -> List[Mapping[str, Any]]:
    """This epoch's weak rows: a seeded permutation per source, read cyclically from epoch * quota."""
    q = quotas({s: len(p) for s, p in pools.items()}, budget)
    drawn: List[Mapping[str, Any]] = []
    for source, pool in sorted(pools.items()):
        n = len(pool)
        if not n or not q[source]:
            continue
        perm = list(range(n))
        random.Random(f"{seed}|weak|{source}").shuffle(perm)
        start = (epoch - 1) * q[source]
        drawn += [pool[perm[(start + j) % n]] for j in range(q[source])]
    return drawn


# --- plan ----------------------------------------------------------------------------------------------


def plan(weak_sha: Mapping[str, str]) -> Dict[str, Any]:
    return {"model_id": MODEL_ID, "labels": list(LABELS), "arms": {k: list(v) for k, v in ARMS.items()},
            "schedule": SCHEDULE, "hyperparameters": HYPER, "selection_rule": SELECTION_RULE,
            "fictional_corpus": hx.VERSION, "weak_corpus_files_sha256": dict(sorted(weak_sha.items())),
            "threshold_tuning": "none; fixed 0.5",
            "never_read_for_training_or_selection": ["weak test bucket", "synthetic_hardening_holdout",
                                                     "exposed fixtures", "locked corpus"]}


def plan_hash(p: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode("utf-8")).hexdigest()


def write_plan(root: Path) -> Dict[str, Any]:
    path = _root(root, "reports", "experiment-plan.json")
    p = plan(weak_manifest_sha(root))
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing["plan_sha256"] != plan_hash(p):
            raise RuntimeError("the predeclared plan differs from the recorded one; it may not change after recording")
        return existing
    if not hx.verify_freeze(root)["ok"]:
        raise RuntimeError("the Task 7B corpus freeze does not verify; nothing is trained")
    for name, digest in weak_manifest_sha(root).items():
        if paths.sha256_file(paths.confined(root, *WEAK_CORPUS, name)) != digest:
            raise RuntimeError("the weak corpus does not match its manifest; rebuild it")
    record = {"plan": p, "plan_sha256": plan_hash(p), "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    paths.write_json(path, record)
    return record


def check_plan(root: Path) -> Dict[str, Any]:
    path = _root(root, "reports", "experiment-plan.json")
    if not path.is_file():
        raise RuntimeError("record the predeclared plan (stage-w-plan) before training")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["plan_sha256"] != plan_hash(plan(weak_manifest_sha(root))):
        raise RuntimeError("code or weak corpus no longer matches the recorded plan")
    return record


# --- loss, prediction, scoring ---------------------------------------------------------------------------


def masked_focal(logits: Any, y: Any, m: Any, gamma: float) -> Any:
    t = tk.torch()
    bce = t.nn.functional.binary_cross_entropy_with_logits(logits, y, reduction="none")
    p = t.sigmoid(logits)
    p_t = p * y + (1 - p) * (1 - y)
    return ((1 - p_t) ** gamma * bce * m).sum() / m.sum().clamp(min=1.0)


def predict(net: Any, tok: Any, rows: Sequence[Mapping[str, Any]], device: str, micro: int = 64
            ) -> Tuple[List[List[float]], Optional[float]]:
    """Probabilities for all nine logits, and the masked plain-BCE loss where rows carry ``y``/``m``."""
    t = tk.torch()
    net.eval()
    probs: List[List[float]] = []
    total, n = 0.0, 0.0
    with t.inference_mode(), t.autocast(device_type="cuda", dtype=t.bfloat16, enabled=device == "cuda"):
        for batch in tk.chunks(list(rows), micro):
            enc = tok([r["text"] for r in batch], max_length=sm.MAX_LEN, truncation=True, padding=True,
                      return_tensors="pt").to(device)
            logits = net(enc["input_ids"], enc["attention_mask"]).float()
            if all("y" in r for r in batch):
                y = t.tensor([r["y"] for r in batch], device=device)
                m = t.tensor([r["m"] for r in batch], device=device)
                bce = t.nn.functional.binary_cross_entropy_with_logits(logits, y, reduction="none")
                total += float((bce * m).sum())
                n += float(m.sum())
            probs += t.sigmoid(logits).cpu().tolist()
    return probs, (total / n if n else None)


def score_detectors(rows: Sequence[Mapping[str, Any]], probs: Sequence[Sequence[float]]) -> Dict[str, Any]:
    gold = [r["gold"] for r in rows]
    pred = [metrics.firings(p[:len(DETECTOR_LABELS)], DETECTOR_LABELS) for p in probs]
    out = metrics.summary(gold, pred, DETECTOR_LABELS)
    out["by_language"] = metrics.by_group(gold, pred, [r["language"] for r in rows], DETECTOR_LABELS)
    return out


def selection_key(result: Mapping[str, Any]) -> Tuple[Any, ...]:
    v = result["validation"]
    return (-(v["macro"]["f1"] or 0.0), -(v["min_label_recall"] or 0.0), result["validation_loss"], result["seed"],
            list(ARMS).index(result["arm"]))


# --- checkpoints --------------------------------------------------------------------------------------------


def save_checkpoint(net: Any, tok: Any, target: Path, config: Mapping[str, Any]) -> Dict[str, str]:
    st = importlib.import_module("safetensors.torch")
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        tk._remove_tree(partial)
    partial.mkdir(parents=True)
    net.encoder.save_pretrained(str(partial / ENCODER_DIR), safe_serialization=True)
    tok.save_pretrained(str(partial / ENCODER_DIR))
    st.save_file({k: v.detach().cpu().contiguous() for k, v in net.head.state_dict().items()}, str(partial / HEAD_FILE))
    (partial / CONFIG_FILE).write_text(json.dumps({**config, "model_id": MODEL_ID, "labels": list(LABELS),
                                                   "threshold": metrics.THRESHOLD, "max_len": sm.MAX_LEN,
                                                   "pooling": "attention-masked mean", "calibrated": False,
                                                   "authoritative": False, "identity": IDENTITY},
                                                  indent=1, sort_keys=True) + "\n", encoding="utf-8")
    hashes = {p.relative_to(partial).as_posix(): paths.sha256_file(p) for p in sorted(partial.rglob("*")) if p.is_file()}
    if target.exists():
        tk._remove_tree(target)
    partial.replace(target)
    return hashes


def load_checkpoint(directory: Path, device: str) -> Dict[str, Any]:
    st = importlib.import_module("safetensors.torch")
    config = json.loads((directory / CONFIG_FILE).read_text(encoding="utf-8"))
    if config.get("model_id") != MODEL_ID or tuple(config.get("labels", ())) != LABELS:
        raise ValueError("checkpoint identity or label order does not match this code")
    net = sm.build_network(sm.load_encoder(directory / ENCODER_DIR), len(LABELS))
    net.head.load_state_dict(st.load_file(str(directory / HEAD_FILE)))
    net.to(device).eval()
    return {"net": net, "tokenizer": tk.load_tokenizer(directory / ENCODER_DIR), "config": config}


# --- training ------------------------------------------------------------------------------------------------


def train_run(root: Path, arm: str, seed: int, train: Sequence[Mapping[str, Any]], val: Sequence[Mapping[str, Any]],
              pools: Mapping[str, Sequence[Mapping[str, Any]]], enc_dir: Path, *, epochs_max: int, smoke: bool,
              log: Any = print) -> Dict[str, Any]:
    t, tf = tk.torch(), tk.transformers()
    tk.seed_everything(seed)
    device = tk.device()
    tok = tk.load_tokenizer(enc_dir)
    net = sm.build_network(sm.load_encoder(enc_dir), len(LABELS)).to(device)
    opt = t.optim.AdamW([{"params": net.encoder.parameters(), "lr": HYPER["encoder_lr"]},
                         {"params": list(net.head.parameters()), "lr": HYPER["head_lr"]}],
                        weight_decay=HYPER["weight_decay"], fused=device == "cuda")
    active = {s: pools[s] for s in ARMS[arm]}
    epoch_size = len(train) + (len(weak_draw(active, len(train), seed, 1)) if active else 0)
    micro, accum = HYPER["micro_batch"], HYPER["grad_accumulation"]
    steps = epochs_max * math.ceil(epoch_size / (micro * accum))
    sched = tf.get_linear_schedule_with_warmup(opt, max(1, int(HYPER["warmup_fraction"] * steps)), steps)
    monitor = tk.Monitor()
    history, best, best_state, stale = [], None, None, 0
    for epoch in range(1, epochs_max + 1):
        started = time.perf_counter()
        net.train()
        order = list(train) + (weak_draw(active, len(train), seed, epoch) if active else [])
        random.Random(f"{seed}|{arm}|epoch{epoch}").shuffle(order)
        running, n_batches = 0.0, 0
        batches = list(tk.chunks(order, micro))
        for i, batch in enumerate(batches):
            enc = tok([r["text"] for r in batch], max_length=HYPER["max_len"], truncation=True, padding=True,
                      return_tensors="pt").to(device)
            y = t.tensor([r["y"] for r in batch], device=device)
            m = t.tensor([r["m"] for r in batch], device=device)
            with t.autocast(device_type="cuda", dtype=t.bfloat16, enabled=device == "cuda"):
                logits = net(enc["input_ids"], enc["attention_mask"])
            loss = masked_focal(logits.float(), y, m, HYPER["gamma"]) / accum
            loss.backward()
            if (i + 1) % accum == 0 or i + 1 == len(batches):
                t.nn.utils.clip_grad_norm_(net.parameters(), HYPER["grad_clip"])
                opt.step()
                sched.step()
                opt.zero_grad(set_to_none=True)
            running += float(loss.detach()) * accum
            n_batches += 1
        monitor.sample()
        probs, val_loss = predict(net, tok, val, device)
        v = score_detectors(val, probs)
        candidate = {"arm": arm, "seed": seed, "epoch": epoch, "validation": v, "validation_loss": val_loss}
        history.append({"epoch": epoch, "rows": len(order), "train_loss": round(running / max(1, n_batches), 5),
                        "validation_loss": round(val_loss, 5), "macro_f1": v["macro"]["f1"],
                        "min_label_recall": v["min_label_recall"],
                        "crisis_recall": v["per_label"]["crisis_self_harm"]["recall"],
                        "epoch_seconds": round(time.perf_counter() - started, 1)})
        log(f"  {arm} seed {seed} epoch {epoch}: rows {len(order)} loss {history[-1]['train_loss']} val loss "
            f"{history[-1]['validation_loss']} macro F1 {v['macro']['f1']} min R {v['min_label_recall']} "
            f"crisis R {history[-1]['crisis_recall']} ({history[-1]['epoch_seconds']} s)")
        if best is None or selection_key(candidate) < selection_key(best):
            best, stale = candidate, 0
            best_state = {part: {k: x.detach().to("cpu", copy=True) for k, x in mod.state_dict().items()}
                          for part, mod in (("encoder", net.encoder), ("head", net.head))}
        else:
            stale += 1
            if stale >= HYPER["patience"]:
                log(f"  {arm} seed {seed}: early stop after epoch {epoch}")
                break
    net.encoder.load_state_dict(best_state["encoder"])
    net.head.load_state_dict(best_state["head"])
    name = f"{arm}-seed-{seed}"
    hashes = save_checkpoint(net, tok, _root(root, "checkpoints", name, smoke=smoke),
                             {"arm": arm, "seed": seed, "epoch": best["epoch"], "stage": "W",
                              "weak_targets": list(ARMS[arm]), "fictional_corpus": hx.VERSION})
    v = best["validation"]
    result = {"arm": arm, "seed": seed, "selected_epoch": best["epoch"], "history": history,
              "validation": {k: v[k] for k in ("macro", "min_label_recall", "micro", "per_label", "by_language")},
              "validation_loss": round(best["validation_loss"], 5), "files_sha256": hashes,
              "checkpoint": "/".join((*(SMOKE_ROOT if smoke else ROOT), "checkpoints", name)),
              "resources": monitor.report(), "weak_quotas": quotas({s: len(p) for s, p in active.items()}, len(train))}
    del net, opt, best_state
    t.cuda.empty_cache()
    return result


def run_phase(root: Path, phase: int, *, smoke: Optional[int] = None, log: Any = print) -> Dict[str, Any]:
    """Train one phase. ``smoke=N`` trains every arm for one epoch on N rows per pool into stage-w-smoke/."""
    is_smoke = smoke is not None
    if not is_smoke:
        check_plan(root)
        if not hx.verify_freeze(root)["ok"]:
            raise RuntimeError("the Task 7B corpus freeze does not verify; nothing is trained")
    enc_dir, stage_a_run = encoder_dir(root)
    train = fictional_rows(hx.load_split(root, "train"))
    val = fictional_rows(hx.load_split(root, "validation"))
    pools = load_weak(root, "train")
    if is_smoke:
        train, val = train[:smoke], val[:smoke]
        pools = {s: p[:smoke] for s, p in pools.items()}
    runs_path = _root(root, "reports", "runs.json", smoke=is_smoke)
    runs = json.loads(runs_path.read_text(encoding="utf-8")) if runs_path.is_file() else {"runs": []}
    if phase == 1:
        todo = [(a, s) for a in SCHEDULE["phase1"]["arms"] for s in SCHEDULE["phase1"]["seeds"]]
    else:
        winner = phase1_winner(runs["runs"])
        todo = [(winner, s) for s in SCHEDULE["phase2"]["seeds"]]
        runs["phase1_winner"] = winner
    done = {(r["arm"], r["seed"]) for r in runs["runs"]}
    for arm, seed in todo:
        if (arm, seed) in done:
            continue
        started = time.perf_counter()
        result = train_run(root, arm, seed, train, val, pools, enc_dir, epochs_max=1 if is_smoke else HYPER["epochs_max"],
                           smoke=is_smoke, log=log)
        result["seconds"] = round(time.perf_counter() - started, 1)
        result["phase"] = phase
        runs["runs"].append(result)
        paths.write_json(runs_path, runs)  # after every run, so a crash loses at most one run
    runs.update({"stage_a_run": stage_a_run, "smoke": is_smoke,
                 "records": {"fictional_train": len(train), "fictional_validation": len(val),
                             "weak_pools": {s: len(p) for s, p in pools.items()}}})
    paths.write_json(runs_path, runs)
    return {"phase": phase, "smoke": is_smoke, "phase1_winner": runs.get("phase1_winner"),
            "runs": [{"arm": r["arm"], "seed": r["seed"], "selected_epoch": r["selected_epoch"],
                      "macro_f1": r["validation"]["macro"]["f1"], "min_label_recall": r["validation"]["min_label_recall"],
                      "crisis_recall": r["validation"]["per_label"]["crisis_self_harm"]["recall"],
                      "validation_loss": r["validation_loss"], "seconds": r["seconds"],
                      "peak_reserved_mb": r["resources"]["peak_reserved_mb"]} for r in runs["runs"]]}


def phase1_winner(runs: Sequence[Mapping[str, Any]]) -> str:
    phase1 = [r for r in runs if r["phase"] == 1]
    if {r["arm"] for r in phase1} != set(SCHEDULE["phase1"]["arms"]):
        raise RuntimeError("phase 1 is incomplete")
    return sorted(phase1, key=selection_key)[0]["arm"]


def select(root: Path) -> Dict[str, Any]:
    runs = json.loads(_root(root, "reports", "runs.json").read_text(encoding="utf-8"))["runs"]
    if not any(r["phase"] == 2 for r in runs):
        raise RuntimeError("phase 2 has not run; selection waits for all seeds")
    ranked = sorted(runs, key=selection_key)
    chosen = ranked[0]
    selection = {"rule": SELECTION_RULE, "uses": "fictional validation only",
                 "ranking": [{"arm": r["arm"], "seed": r["seed"], "epoch": r["selected_epoch"],
                              "macro_f1": r["validation"]["macro"]["f1"],
                              "min_label_recall": r["validation"]["min_label_recall"],
                              "validation_loss": r["validation_loss"]} for r in ranked],
                 "selected": {"arm": chosen["arm"], "seed": chosen["seed"], "epoch": chosen["selected_epoch"],
                              "checkpoint": chosen["checkpoint"]}}
    paths.write_json(_root(root, "reports", "selection.json"), selection)
    paths.write_json(_root(root, "checkpoints", "SELECTED.json"),
                     {**selection["selected"], "model_id": MODEL_ID, "rule": SELECTION_RULE})
    return selection
