"""Task 7B: targeted Stage C retraining on the frozen hardening corpus, selection and promotion gates.

    python -m ml.training.cli stage-c7b-plan      # write the predeclared plan (refuses to change it later)
    python -m ml.training.cli stage-c7b --phase 1 # one seed per configuration
    python -m ml.training.cli stage-c7b --phase 2 # two more seeds of the configuration chosen on validation
    python -m ml.training.cli stage-c7b-evaluate  # once: holdout, gates, status, Task 7 comparison, regression

Everything here reuses the verified Task 7 Stage A encoder. Stage A and Stage B are not repeated,
no external record is added to SAHAY-labelled training, and only the fictional Task 7B train and
validation splits are read during training and selection. The ``synthetic_hardening_holdout`` is
read once, after selection is final. Thresholds stay at a fixed 0.5 and are never tuned.

Predeclared configurations:
- **A:** plain BCE-with-logits with a deterministic class-balanced sampler. Each epoch draws the
  train size with replacement, weighting each record by its rarest positive label, or by the
  no-alert class for an all-negative record.
- **B:** BCE with a per-label `pos_weight` equal to negatives/positives in the Task 7B train split,
  bounded to [1, 8].
- **C:** focal loss with gamma 2.0 and no alpha. It is fixed before training because easy
  negatives dominate the near-miss-heavy corpus; the focal term down-weights them, while class
  weighting (B) and resampling (A) instead change the prior.

Schedule, fixed because six full runs are too costly on the laptop: phase 1 runs seed 13 for A, B
and C; the configuration that wins on validation then gets seeds 42 and 97 in phase 2. Every run
uses the same splits, a 128-token maximum length, micro-batch 16 with gradient accumulation 2,
at most 20 epochs, patience 3, encoder learning rate 3e-5 and head learning rate 1e-3.

Selection uses validation only, both across epochs within a run and across runs:
1. higher crisis recall;
2. higher minimum recall across crisis, legal urgency and coercion;
3. higher macro F1;
4. higher no-alert specificity;
5. lower validation loss (plain BCE, comparable across losses);
6. lower seed.
"""

import hashlib
import json
import math
import random
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..shadow import model as sm
from . import hardening as hx, metrics, paths, torchkit as tk
from .stage_c import encoder_dir, score

CONFIGS: Dict[str, Dict[str, Any]] = {
    "A": {"loss": "bce", "sampler": "class_balanced"},
    "B": {"loss": "bce_pos_weight", "pos_weight_bounds": [1.0, 8.0], "sampler": "shuffle"},
    "C": {"loss": "focal", "gamma": 2.0, "alpha": None, "sampler": "shuffle"},
}
SCHEDULE = {"phase1": {"seeds": [13], "configs": ["A", "B", "C"]}, "phase2": {"seeds": [42, 97], "configs": "winner"}}
HYPER = {"max_len": sm.MAX_LEN, "micro_batch": 16, "grad_accumulation": 2, "epochs_max": 20, "patience": 3,
         "encoder_lr": 3e-5, "head_lr": 1e-3, "weight_decay": 0.01, "warmup_fraction": 0.06, "grad_clip": 1.0,
         "threshold": metrics.THRESHOLD}
WEAK = ("crisis_self_harm", "legal_urgency", "communication_safety_coercion")
SELECTION_RULE = ["higher crisis recall", "higher minimum recall across crisis, legal urgency and coercion",
                  "higher macro F1", "higher no-alert specificity", "lower validation loss (plain BCE)",
                  "lower numeric seed"]
#: Research gates for ``candidate_for_human_review``. Frozen in the plan before training; never lowered.
GATES = {"holdout_crisis_recall_min": 0.80, "per_language_crisis_recall_min": 0.70, "legal_urgency_recall_min": 0.70,
         "coercion_recall_min": 0.70, "macro_f1_min": 0.70, "no_alert_specificity_min": 0.90,
         "repeat_agreement": 1.0}
ROOT = ("task7b",)


def _root(root: Path, *parts: str) -> Path:
    return paths.confined(root, *ROOT, *parts)


def plan() -> Dict[str, Any]:
    return {"configs": CONFIGS, "schedule": SCHEDULE, "hyperparameters": HYPER, "selection_rule": SELECTION_RULE,
            "gates": GATES, "threshold_tuning": "none; fixed 0.5", "corpus_version": hx.VERSION,
            "holdout_use": "evaluated once after selection; never used for selection or thresholds"}


def plan_hash(p: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode("utf-8")).hexdigest()


def write_plan(root: Path) -> Dict[str, Any]:
    path = _root(root, "reports", "experiment-plan.json")
    p = plan()
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing["plan_sha256"] != plan_hash(p):
            raise RuntimeError("the predeclared plan differs from the recorded one; it may not change after recording")
        return existing
    freeze = hx.verify_freeze(root)
    if not freeze["ok"]:
        raise RuntimeError("the Task 7B corpus freeze does not verify; nothing is trained")
    record = {"plan": p, "plan_sha256": plan_hash(p), "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "corpus_freeze": {"version": freeze["version"], "frozen_at": freeze["frozen_at"]}}
    paths.write_json(path, record)
    return record


def check_plan(root: Path) -> Dict[str, Any]:
    path = _root(root, "reports", "experiment-plan.json")
    if not path.is_file():
        raise RuntimeError("write the predeclared plan before training")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["plan_sha256"] != plan_hash(plan()):
        raise RuntimeError("code no longer matches the recorded plan")
    return record


# --- data and losses ---------------------------------------------------------------------------------


def rows(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out = [{"id": r["id"], "text": sm.model_text(r["turns"]), "labels": [float(r["labels"][n]) for n in sm.LABELS],
            "gold": dict(r["labels"]), "language": r["language"], "family": r["family"],
            "group": r["contrast_group"], "negatives": r["negative_labels"], "slices": r["challenge_slices"]}
           for r in records]
    return sorted(out, key=lambda r: r["id"])


def label_frequencies(train: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    c: Counter = Counter()
    for r in train:
        pos = [n for n, v in zip(sm.LABELS, r["labels"]) if v]
        for n in pos:
            c[n] += 1
        if not pos:
            c["no_alert"] += 1
    return dict(c)


def balanced_order(train: Sequence[Mapping[str, Any]], seed: int, epoch: int) -> List[int]:
    freq = label_frequencies(train)
    weights = []
    for r in train:
        pos = [n for n, v in zip(sm.LABELS, r["labels"]) if v]
        weights.append(max(1.0 / freq[n] for n in pos) if pos else 1.0 / freq["no_alert"])
    return random.Random(f"{seed}|balanced|{epoch}").choices(range(len(train)), weights=weights, k=len(train))


def pos_weights(train: Sequence[Mapping[str, Any]], bounds: Sequence[float]) -> List[float]:
    n = len(train)
    out = []
    for i, _ in enumerate(sm.LABELS):
        pos = sum(r["labels"][i] for r in train)
        raw = (n - pos) / pos if pos else bounds[1]
        out.append(round(min(max(raw, bounds[0]), bounds[1]), 4))
    return out


def loss_fn(config: Mapping[str, Any], logits: Any, y: Any, pw: Optional[Any]) -> Any:
    t = tk.torch()
    f = t.nn.functional
    if config["loss"] == "bce":
        return f.binary_cross_entropy_with_logits(logits, y)
    if config["loss"] == "bce_pos_weight":
        return f.binary_cross_entropy_with_logits(logits, y, pos_weight=pw)
    bce = f.binary_cross_entropy_with_logits(logits, y, reduction="none")
    p = t.sigmoid(logits)
    p_t = p * y + (1 - p) * (1 - y)
    return ((1 - p_t) ** config["gamma"] * bce).mean()


# --- metrics beyond the Task 7 summary ------------------------------------------------------------------


def no_alert_specificity(rows_: Sequence[Mapping[str, Any]], fired: Sequence[Mapping[str, bool]]) -> Optional[float]:
    idx = [i for i, r in enumerate(rows_) if not any(r["gold"].values())]
    if not idx:
        return None
    return round(sum(not any(fired[i].values()) for i in idx) / len(idx), 4)


def evaluate_rows(rows_: Sequence[Mapping[str, Any]], probs: Sequence[Sequence[float]]) -> Dict[str, Any]:
    fired = [metrics.firings(p, sm.LABELS) for p in probs]
    s = score(rows_, probs)
    per = s["per_label"]
    weak = [per[n]["recall"] for n in WEAK if per[n]["recall"] is not None]
    s["crisis_recall"] = per["crisis_self_harm"]["recall"]
    s["min_weak_recall"] = min(weak) if weak else None
    s["no_alert_specificity"] = no_alert_specificity(rows_, fired)
    s["crisis_recall_by_language"] = {}
    for lang in hx.LANGUAGES:
        idx = [i for i, r in enumerate(rows_) if r["language"] == lang and r["gold"]["crisis_self_harm"]]
        s["crisis_recall_by_language"][lang] = (round(sum(fired[i]["crisis_self_harm"] for i in idx) / len(idx), 4)
                                                if idx else None)
    s["contrast"] = contrast_accuracy(rows_, fired)
    s["errors"] = {"fp": sum(per[n]["fp"] for n in sm.LABELS), "fn": sum(per[n]["fn"] for n in sm.LABELS)}
    return s


def contrast_accuracy(rows_: Sequence[Mapping[str, Any]], fired: Sequence[Mapping[str, bool]]) -> Dict[str, Any]:
    """Per contrast group: every member correct on the group's focus labels (its positives and its
    explicit near-miss negatives). Reported as group-level and member-level accuracy."""
    groups: Dict[str, List[bool]] = {}
    for r, f in zip(rows_, fired):
        if r["group"].startswith("combo:"):
            continue
        focus = set(r["negatives"]) | {n for n, v in r["gold"].items() if v}
        if not focus:
            continue
        groups.setdefault(r["group"], []).append(all(bool(f[n]) == bool(r["gold"][n]) for n in focus))
    members = [ok for v in groups.values() for ok in v]
    return {"groups": len(groups), "groups_all_correct": sum(all(v) for v in groups.values()),
            "member_accuracy": round(sum(members) / len(members), 4) if members else None}


def selection_key(result: Mapping[str, Any]) -> Tuple[Any, ...]:
    v = result["validation"]
    return (-(v["crisis_recall"] or 0.0), -(v["min_weak_recall"] or 0.0), -(v["macro"]["f1"] or 0.0),
            -(v["no_alert_specificity"] or 0.0), result["validation_loss"], result["seed"])


# --- training --------------------------------------------------------------------------------------------


def train_run(root: Path, config_name: str, seed: int, train: Sequence[Mapping[str, Any]],
              val: Sequence[Mapping[str, Any]], enc_dir: Path, log: Any = print) -> Dict[str, Any]:
    t, tf = tk.torch(), tk.transformers()
    config = CONFIGS[config_name]
    tk.seed_everything(seed)
    device = tk.device()
    tok = tk.load_tokenizer(enc_dir)
    net = sm.build_network(sm.load_encoder(enc_dir)).to(device)
    opt = t.optim.AdamW([{"params": net.encoder.parameters(), "lr": HYPER["encoder_lr"]},
                         {"params": list(net.head.parameters()), "lr": HYPER["head_lr"]}],
                        weight_decay=HYPER["weight_decay"], fused=device == "cuda")
    micro, accum = HYPER["micro_batch"], HYPER["grad_accumulation"]
    steps = HYPER["epochs_max"] * math.ceil(len(train) / (micro * accum))
    sched = tf.get_linear_schedule_with_warmup(opt, max(1, int(HYPER["warmup_fraction"] * steps)), steps)
    pw = (t.tensor(pos_weights(train, config["pos_weight_bounds"]), device=device)
          if config["loss"] == "bce_pos_weight" else None)
    monitor = tk.Monitor()
    history, best, best_state, stale = [], None, None, 0
    for epoch in range(1, HYPER["epochs_max"] + 1):
        net.train()
        if config["sampler"] == "class_balanced":
            order = [train[i] for i in balanced_order(train, seed, epoch)]
        else:
            order = list(train)
            random.Random(f"{seed}|epoch{epoch}").shuffle(order)
        running, n_batches = 0.0, 0
        batches = list(tk.chunks(order, micro))
        for i, batch in enumerate(batches):
            enc = tok([r["text"] for r in batch], max_length=HYPER["max_len"], truncation=True, padding=True,
                      return_tensors="pt").to(device)
            y = t.tensor([r["labels"] for r in batch], device=device)
            with t.autocast(device_type="cuda", dtype=t.bfloat16, enabled=device == "cuda"):
                logits = net(enc["input_ids"], enc["attention_mask"])
            loss = loss_fn(config, logits.float(), y, pw) / accum
            loss.backward()
            if (i + 1) % accum == 0 or i + 1 == len(batches):
                t.nn.utils.clip_grad_norm_(net.parameters(), HYPER["grad_clip"])
                opt.step()
                sched.step()
                opt.zero_grad(set_to_none=True)
            running += float(loss.detach()) * accum
            n_batches += 1
        monitor.sample()
        from .stage_c import predict
        probs, val_loss = predict(net, tok, val, device)
        v = evaluate_rows(val, probs)
        candidate = {"seed": seed, "epoch": epoch, "validation": v, "validation_loss": val_loss}
        history.append({"epoch": epoch, "train_loss": round(running / max(1, n_batches), 5),
                        "validation_loss": round(val_loss, 5), "crisis_recall": v["crisis_recall"],
                        "min_weak_recall": v["min_weak_recall"], "macro_f1": v["macro"]["f1"],
                        "no_alert_specificity": v["no_alert_specificity"]})
        log(f"  {config_name} seed {seed} epoch {epoch}: loss {history[-1]['train_loss']} val loss "
            f"{history[-1]['validation_loss']} crisis R {v['crisis_recall']} weak min R {v['min_weak_recall']} "
            f"macro F1 {v['macro']['f1']} no-alert spec {v['no_alert_specificity']}")
        if best is None or selection_key(candidate) < selection_key(best):
            best, stale = candidate, 0
            best_state = {part: {k: v_.detach().to("cpu", copy=True) for k, v_ in m.state_dict().items()}
                          for part, m in (("encoder", net.encoder), ("head", net.head))}
        else:
            stale += 1
            if stale >= HYPER["patience"]:
                log(f"  {config_name} seed {seed}: early stop after epoch {epoch}")
                break
    net.encoder.load_state_dict(best_state["encoder"])
    net.head.load_state_dict(best_state["head"])
    target = _root(root, "checkpoints", f"{config_name}-seed-{seed}")
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        tk._remove_tree(partial)
    sm.save(net, tok, partial, {"seed": seed, "epoch": best["epoch"], "stage": "C7B", "config": config_name,
                                "corpus_version": hx.VERSION})
    hashes = {p.relative_to(partial).as_posix(): paths.sha256_file(p) for p in sorted(partial.rglob("*")) if p.is_file()}
    if target.exists():
        tk._remove_tree(target)
    partial.replace(target)
    result = {"config": config_name, "seed": seed, "selected_epoch": best["epoch"], "history": history,
              "validation": {k: v for k, v in best["validation"].items() if k != "per_label"} |
              {"per_label": best["validation"]["per_label"]},
              "validation_loss": round(best["validation_loss"], 5), "files_sha256": hashes,
              "checkpoint": f"task7b/checkpoints/{config_name}-seed-{seed}", "resources": monitor.report(),
              "pos_weights": pos_weights(train, CONFIGS["B"]["pos_weight_bounds"]) if config_name == "B" else None}
    del net, opt, best_state
    tk.torch().cuda.empty_cache()
    return result


def run_phase(root: Path, phase: int, log: Any = print) -> Dict[str, Any]:
    check_plan(root)
    if not hx.verify_freeze(root)["ok"]:
        raise RuntimeError("the Task 7B corpus freeze does not verify; nothing is trained")
    enc_dir, stage_a_run = encoder_dir(root)
    train, val = rows(hx.load_split(root, "train")), rows(hx.load_split(root, "validation"))
    runs_path = _root(root, "reports", "runs.json")
    runs = json.loads(runs_path.read_text(encoding="utf-8")) if runs_path.is_file() else {"runs": []}
    if phase == 1:
        todo = [(c, s) for c in SCHEDULE["phase1"]["configs"] for s in SCHEDULE["phase1"]["seeds"]]
    else:
        winner = phase1_winner(runs["runs"])
        todo = [(winner, s) for s in SCHEDULE["phase2"]["seeds"]]
        runs["phase1_winner"] = winner
    done = {(r["config"], r["seed"]) for r in runs["runs"]}
    for config_name, seed in todo:
        if (config_name, seed) in done:
            continue
        started = time.perf_counter()
        result = train_run(root, config_name, seed, train, val, enc_dir, log)
        result["seconds"] = round(time.perf_counter() - started, 1)
        result["phase"] = phase
        runs["runs"].append(result)
        paths.write_json(runs_path, runs)  # after every run, so a crash loses at most one run
    runs["stage_a_run"] = stage_a_run
    runs["records"] = {"train": len(train), "validation": len(val)}
    paths.write_json(runs_path, runs)
    return {"phase": phase, "runs": [{k: r[k] for k in ("config", "seed", "selected_epoch", "validation_loss", "seconds")}
                                     | {"crisis_recall": r["validation"]["crisis_recall"],
                                        "min_weak_recall": r["validation"]["min_weak_recall"],
                                        "macro_f1": r["validation"]["macro"]["f1"],
                                        "no_alert_specificity": r["validation"]["no_alert_specificity"],
                                        "peak_reserved_mb": r["resources"]["peak_reserved_mb"]} for r in runs["runs"]],
            "phase1_winner": runs.get("phase1_winner")}


def phase1_winner(runs: Sequence[Mapping[str, Any]]) -> str:
    phase1 = [r for r in runs if r["phase"] == 1]
    if {r["config"] for r in phase1} != set(SCHEDULE["phase1"]["configs"]):
        raise RuntimeError("phase 1 is incomplete")
    return sorted(phase1, key=selection_key)[0]["config"]


def select(root: Path) -> Dict[str, Any]:
    runs = json.loads(_root(root, "reports", "runs.json").read_text(encoding="utf-8"))["runs"]
    ranked = sorted(runs, key=selection_key)
    chosen = ranked[0]
    selection = {"rule": SELECTION_RULE, "uses": "validation only",
                 "ranking": [{"config": r["config"], "seed": r["seed"], "epoch": r["selected_epoch"],
                              "crisis_recall": r["validation"]["crisis_recall"],
                              "min_weak_recall": r["validation"]["min_weak_recall"],
                              "macro_f1": r["validation"]["macro"]["f1"],
                              "no_alert_specificity": r["validation"]["no_alert_specificity"],
                              "validation_loss": r["validation_loss"]} for r in ranked],
                 "selected": {"config": chosen["config"], "seed": chosen["seed"], "epoch": chosen["selected_epoch"]}}
    paths.write_json(_root(root, "reports", "selection.json"), selection)
    paths.write_json(_root(root, "checkpoints", "SELECTED.json"),
                     {"config": chosen["config"], "seed": chosen["seed"], "checkpoint": chosen["checkpoint"],
                      "model_id": sm.MODEL_ID, "rule": SELECTION_RULE})
    return selection


# --- promotion gates ------------------------------------------------------------------------------------


def gate_results(holdout: Mapping[str, Any], repeat_agreement: float, invariance_ok: bool, packet_ready: bool,
                 nothing_committed: bool) -> Dict[str, Any]:
    per = holdout["per_label"]
    by_lang = holdout["crisis_recall_by_language"]
    checks = {
        "holdout_crisis_recall": (holdout["crisis_recall"], GATES["holdout_crisis_recall_min"]),
        "crisis_recall_en": (by_lang.get("en"), GATES["per_language_crisis_recall_min"]),
        "crisis_recall_hi": (by_lang.get("hi"), GATES["per_language_crisis_recall_min"]),
        "crisis_recall_hinglish": (by_lang.get("hinglish"), GATES["per_language_crisis_recall_min"]),
        "legal_urgency_recall": (per["legal_urgency"]["recall"], GATES["legal_urgency_recall_min"]),
        "coercion_recall": (per["communication_safety_coercion"]["recall"], GATES["coercion_recall_min"]),
        "macro_f1": (holdout["macro"]["f1"], GATES["macro_f1_min"]),
        "no_alert_specificity": (holdout["no_alert_specificity"], GATES["no_alert_specificity_min"]),
        "repeat_agreement": (repeat_agreement, GATES["repeat_agreement"]),
    }
    out = {k: {"value": v, "required": req, "passed": v is not None and v >= req} for k, (v, req) in checks.items()}
    macro = holdout["macro"]
    out["macro_f1"].update({"labels_included": macro.get("f1_labels_included"),
                            "defined_labels": macro.get("f1_defined_labels"),
                            "labels_excluded_undefined": macro.get("f1_labels_excluded_undefined")})
    # A validity condition, not a threshold: every schema label needs positive and negative support
    # before any promotion conclusion is possible. A report without coverage counts as incomplete.
    coverage = holdout.get("coverage") or {}
    out["full_label_coverage"] = {"value": bool(coverage.get("full_label_coverage")),
                                  "labels_missing_positive_support": coverage.get("labels_missing_positive_support"),
                                  "labels_missing_negative_support": coverage.get("labels_missing_negative_support"),
                                  "passed": bool(coverage.get("full_label_coverage"))}
    out["deterministic_invariance"] = {"value": invariance_ok, "passed": bool(invariance_ok)}
    out["review_packet_prepared"] = {"value": packet_ready, "passed": bool(packet_ready)}
    out["nothing_committed"] = {"value": nothing_committed, "passed": bool(nothing_committed)}
    return out


REJECTED = "rejected_for_product_integration"
CANDIDATE = "candidate_for_human_review"
#: The Task 7B checkpoint (``7b-v1``, configuration C, seed 13) is permanently rejected: its frozen
#: holdout had no positive support for three labels and it missed the macro-F1 gate.
TASK7B_CHECKPOINT_STATUS = REJECTED


def status_from(gates: Mapping[str, Any]) -> str:
    """The reusable, pure promotion evaluator.

    Returns ``candidate_for_human_review`` only when every gate passes, including full eight-label
    coverage; anything else, or a report without the coverage gate, is ``rejected_for_product_integration``.
    ``candidate_for_human_review`` is never a product, backend, frontend, mobile or victim-facing
    approval (see ``status_record``).
    """
    if "full_label_coverage" not in gates:
        return REJECTED
    return CANDIDATE if all(g["passed"] for g in gates.values()) else REJECTED


def status_record(status: str, gates: Mapping[str, Any], checkpoint: str) -> Dict[str, Any]:
    """The private status record. Integration flags are false for every status, including a candidate."""
    if status not in (REJECTED, CANDIDATE):
        status = REJECTED
    return {"model_id": sm.MODEL_ID, "checkpoint": checkpoint, "deployment_status": status,
            "promotion_gates_passed": status == CANDIDATE, "gates": dict(gates),
            "backend_integration_allowed": False, "frontend_integration_allowed": False,
            "mobile_integration_allowed": False, "victim_facing_allowed": False, "shadow_local_demo_only": True,
            "human_review_completed": False, "numeric_promotion_threshold_approved": False,
            "note": "candidate_for_human_review, if ever reached, only permits human review; it is not product "
                    "integration approval"}


PROMOTION_STATEMENT = ("The checkpoint remains rejected for product integration. It missed the macro-F1 gate, and "
                       "full eight-label promotion evaluation was not possible because three labels had no positive "
                       "holdout support.")


def correct_holdout_report(root: Path) -> Dict[str, Any]:
    """Metric-validity correction of the once-only Task 7B evaluation, from its stored per-label counts.

    Nothing is re-predicted and nothing about the holdout changes. The original report and status
    are preserved byte for byte (the status is copied aside before it is extended). The corrected
    report adds coverage, denominators, null reasons and the macro-F1 label sets, and recomputes the
    gates with the coverage condition. No numeric threshold changes.
    """
    original_path = _root(root, "reports", "holdout-evaluation.json")
    original_bytes = original_path.read_bytes()
    original = json.loads(original_bytes.decode("utf-8"))
    freeze = hx.verify_freeze(root)
    if not freeze["ok"]:
        raise RuntimeError("the frozen Task 7B holdout no longer verifies; nothing is corrected")
    stored = original["holdout"]
    rows = {n: metrics.label_metrics(*(stored["per_label"][n][k] for k in ("tp", "fp", "fn", "tn")))
            for n in sm.LABELS}
    corrected = metrics.summary_from_rows(rows, sm.LABELS, stored["records"])
    for key in ("crisis_recall", "crisis_recall_by_language", "no_alert_specificity", "contrast", "exact_match",
                "hamming_loss", "errors", "min_weak_recall"):
        corrected[key] = stored.get(key)
    gates = gate_results(corrected, original["repeat_agreement"], original["invariance"]["identical"],
                         original["gates"]["review_packet_prepared"]["passed"],
                         original["gates"]["nothing_committed"]["passed"])
    status = status_from(gates)  # the same reusable evaluator; here its inputs are Task 7B's recorded counts
    if status != TASK7B_CHECKPOINT_STATUS:
        raise RuntimeError("the recorded Task 7B counts no longer reproduce its permanent rejected status; the "
                           "evaluation inputs must have changed, so nothing is corrected")
    coverage = corrected["coverage"]
    threat = rows["continuing_threat"]
    promotion = {
        "deployment_status": status,
        "macro_f1_threshold_met": gates["macro_f1"]["passed"],
        "macro_f1": {"value": corrected["macro"]["f1"], "required": GATES["macro_f1_min"],
                     "labels_included": corrected["macro"]["f1_labels_included"],
                     "defined_labels": corrected["macro"]["f1_defined_labels"],
                     "labels_excluded_undefined": corrected["macro"]["f1_labels_excluded_undefined"],
                     "calculation": "mean F1 over the labels with positive holdout support; undefined labels "
                                    "excluded, never zero-filled (the original 0.6747 was computed the same way)"},
        "full_eight_label_evaluation_complete": coverage["promotion_metrics_fully_evaluable"],
        "labels_without_positive_support": coverage["labels_missing_positive_support"],
        "no_promotion_conclusion_for": coverage["labels_missing_positive_support"],
        "continuing_threat_recall": {"value": threat["recall"], "positives": threat["positives"],
                                     "recall_denominator": threat["denominators"]["recall"]},
        "human_review": "pending",
        "statement": PROMOTION_STATEMENT,
    }
    report = {"corrects": "reports/holdout-evaluation.json",
              "original_sha256": hashlib.sha256(original_bytes).hexdigest(),
              "holdout_freeze": {"version": freeze["version"], "frozen_at": freeze["frozen_at"], "verified": True},
              "holdout": corrected, "gates": gates, "promotion": promotion,
              "evidence_class": original["evidence_class"], "retrained": False, "holdout_changed": False}
    paths.write_json(_root(root, "reports", "holdout-evaluation-corrected.json"), report)
    status_path = _root(root, "STATUS.json")
    backup = _root(root, "STATUS.pre-correction.json")
    if status_path.is_file() and not backup.is_file():
        backup.write_bytes(status_path.read_bytes())
    current = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
    current.update({"deployment_status": status, "promotion_gates_passed": False, "gates": gates,
                    "full_label_coverage": coverage["full_label_coverage"],
                    "promotion_metrics_fully_evaluable": coverage["promotion_metrics_fully_evaluable"],
                    "labels_missing_positive_support": coverage["labels_missing_positive_support"],
                    "promotion_statement": PROMOTION_STATEMENT, "human_review_completed": False})
    paths.write_json(status_path, current)
    return {"status": status, "promotion": promotion, "coverage": coverage,
            "original_report_unchanged": hashlib.sha256(original_path.read_bytes()).hexdigest()
            == report["original_sha256"]}


# --- retention ------------------------------------------------------------------------------------------


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0


def retention_proposal(root: Path) -> Dict[str, Any]:
    """A private list of artefacts with sizes and a keep/review suggestion. Deletes nothing."""
    selected = json.loads(_root(root, "checkpoints", "SELECTED.json").read_text(encoding="utf-8"))["checkpoint"]
    rows: List[Dict[str, Any]] = []

    def add(rel: str, role: str, suggestion: str) -> None:
        path = paths.confined(root, *rel.split("/"))
        if path.exists():
            rows.append({"path": f"{paths.ROOT_LABEL}/{rel}", "role": role, "bytes": _size(path),
                         "suggestion": suggestion})

    add(selected, "selected Task 7B checkpoint", "keep while the experiment is active")
    stage_a = json.loads(paths.confined(root, "checkpoints", "stage-a", "SELECTED.json").read_text(encoding="utf-8"))
    add(stage_a["checkpoint"], "Stage A encoder (selected)", "keep: every Stage C run depends on it")
    run_id = stage_a["run_id"]
    add(f"checkpoints/stage-a/{run_id}/coverage", "Stage A post-coverage checkpoint", "candidate for deletion")
    add(f"checkpoints/stage-a/{run_id}/training_state.pt", "Stage A optimizer and scheduler state",
        "candidate for deletion (only needed to resume Stage A)")
    for p in sorted(paths.confined(root, "checkpoints", "stage-a").iterdir()):
        if p.is_dir() and p.name != run_id:
            add(f"checkpoints/stage-a/{p.name}", "Stage A smoke run", "candidate for deletion")
    t7 = json.loads(paths.confined(root, "checkpoints", "stage-c", "SELECTED.json").read_text(encoding="utf-8"))
    add(t7["checkpoint"], "Task 7 selected checkpoint (rejected_for_product_integration)", "keep for comparison")
    for p in sorted(paths.confined(root, "checkpoints", "stage-c").glob("run*-seed-*")):
        rel = f"checkpoints/stage-c/{p.name}"
        if rel != t7["checkpoint"]:
            add(rel, "rejected Task 7 checkpoint", "candidate for deletion")
    add("checkpoints/stage-b", "Stage B isolated diagnostic heads", "candidate for deletion")
    for p in sorted(_root(root, "checkpoints").glob("*-seed-*")):
        rel = f"task7b/checkpoints/{p.name}"
        if rel != selected:
            add(rel, "rejected Task 7B checkpoint", "candidate for deletion")
    add("corpora/external-ext119-v1", "EXT-119 external training corpus (quarantined)", "review against EXT-119")
    add("corpora/fictional-sahay-v1", "Task 7 fictional corpus (now exposed)", "keep (small)")
    add(f"task7b/corpus/{hx.VERSION}", "Task 7B fictional corpus and frozen holdout", "keep (small)")
    add(f"task7b/review/{hx.VERSION}", "Task 7B human-review packet (pending)", "keep until reviewed")
    add("reports", "Task 7 reports", "keep (small)")
    add("task7b/reports", "Task 7B reports", "keep (small)")
    recoverable = sum(r["bytes"] for r in rows if r["suggestion"].startswith("candidate for deletion"))
    proposal = {"rows": rows, "recoverable_bytes": recoverable, "automatic_deletion": False,
                "note": "A proposal only. Nothing is deleted automatically; the owner decides."}
    paths.write_json(_root(root, "reports", "retention-proposal.json"), proposal)
    return {"items": len(rows), "recoverable_gib": round(recoverable / 2**30, 2), "automatic_deletion": False}


# --- the once-only evaluation --------------------------------------------------------------------------


def _predict_dir(directory: Path, rows_: Sequence[Mapping[str, Any]]) -> List[List[float]]:
    from .stage_c import predict
    device = tk.device()
    bundle = sm.load(directory, device)
    probs, _ = predict(bundle["net"], bundle["tokenizer"], rows_, device)
    del bundle
    tk.torch().cuda.empty_cache()
    return probs


def invariance_evidence(root: Path, sample: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The authoritative deterministic result must be identical whether the shadow model fires,
    stays silent, fails, is missing, times out or returns malformed output."""
    from ..shadow import demo
    from ..shadow.classifier import ShadowClassifier

    def raise_(exc: BaseException) -> Any:
        raise exc

    def fake(infer: Any) -> ShadowClassifier:
        return ShadowClassifier(str(root), "cpu", loader=lambda d, dev_: {"infer_logits": infer},
                                checkpoint_set="task7b")

    variants = {
        "real_model": ShadowClassifier(str(root), checkpoint_set="task7b"),
        "fires": fake(lambda texts: [[9.0] * len(sm.LABELS) for _ in texts]),
        "silent": fake(lambda texts: [[-9.0] * len(sm.LABELS) for _ in texts]),
        "fails": fake(lambda texts: raise_(RuntimeError("boom"))),
        "times_out": fake(lambda texts: raise_(TimeoutError())),
        "malformed": fake(lambda texts: [[float("nan")] for _ in texts]),
        "missing": ShadowClassifier(str(root / "no-such-root"), "cpu"),
    }
    mismatches = 0
    for r in sample:
        turns = [dict(t) for t in r["turns"]]
        outs = [demo.side_by_side(turns, "mobile_chat", clf)["authoritative_deterministic"] for clf in variants.values()]
        mismatches += any(o != outs[0] for o in outs)
    for clf in variants.values():
        clf.unload()
    return {"records": len(sample), "variants": list(variants), "mismatches": mismatches, "identical": mismatches == 0}


def nothing_committed() -> bool:
    repo = Path(__file__).resolve().parents[2]
    tracked = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True).stdout.split()
    return not any(p.endswith((".safetensors", ".pt", ".bin")) or "task7b/" in p
                   or (p.endswith(".jsonl") and not p.startswith("ml/eval/reviews/")) for p in tracked)


def evaluate(root: Path) -> Dict[str, Any]:
    out_path = _root(root, "reports", "holdout-evaluation.json")
    if out_path.is_file():
        raise RuntimeError("the holdout has already been evaluated once; it is not evaluated again")
    check_plan(root)
    freeze = hx.verify_freeze(root)
    if not freeze["ok"]:
        raise RuntimeError("the Task 7B corpus freeze does not verify")
    selection = json.loads(_root(root, "reports", "selection.json").read_text(encoding="utf-8"))
    pointer = json.loads(_root(root, "checkpoints", "SELECTED.json").read_text(encoding="utf-8"))
    chosen = paths.confined(root, *pointer["checkpoint"].split("/"))
    holdout_records = hx.load_split(root, "synthetic_hardening_holdout")
    holdout = rows(holdout_records)
    first = _predict_dir(chosen, holdout)
    second = _predict_dir(chosen, holdout)
    repeat = sum(a == b for a, b in zip(first, second)) / len(first)
    result = evaluate_rows(holdout, first)
    t7_pointer = json.loads(paths.confined(root, "checkpoints", "stage-c", "SELECTED.json").read_text(encoding="utf-8"))
    t7 = evaluate_rows(holdout, _predict_dir(paths.confined(root, *t7_pointer["checkpoint"].split("/")), holdout))
    sample = ([r for r in holdout_records if r["labels"]["crisis_self_harm"]][:40]
              + [r for r in holdout_records if not any(r["labels"].values())][:20])
    invariance = invariance_evidence(root, sample)
    packet = json.loads(paths.confined(root, *hx.REVIEW_DIR, "review-summary.json").read_text(encoding="utf-8"))
    gates = gate_results(result, repeat, invariance["identical"], packet["items"] > 0, nothing_committed())
    status = status_from(gates)
    report = {"selected": selection["selected"], "holdout_version": freeze["version"], "evaluated_once": True,
              "holdout": result, "repeat_agreement": repeat, "task7_checkpoint_on_holdout": t7,
              "invariance": invariance, "gates": gates, "deployment_status": status,
              "evidence_class": "synthetic development evidence on the frozen agent-generated holdout; not "
                                "independent, official, blind, human-authored or clinically validated"}
    paths.write_json(out_path, report)
    paths.write_json(_root(root, "STATUS.json"), status_record(status, gates, pointer["checkpoint"]))
    from . import regression
    from ..shadow.classifier import ShadowClassifier
    shadow = ShadowClassifier(str(root), checkpoint_set="task7b")
    regress: Dict[str, Any] = {name.replace(".json", ""): regression.compare(regression._load(name)["samples"], shadow)
                               for name in regression.CORPORA}
    rt = []
    for c in regression._load(regression.REDTEAM)["cases"]:
        if c["kind"] != "victim_input":
            continue
        res = shadow.classify([{"speaker": "victim", "text": c["text"]}])
        fired = None if res.development_firings is None else res.development_firings["crisis_self_harm"]
        rt.append({"id": c["id"], "expected": c["expected"].get("crisis_precheck"), "fired": fired,
                   "matches": fired == c["expected"].get("crisis_precheck")})
    shadow.unload()
    regress["redteam_victim_input"] = {"cases": len(rt), "matches": sum(r["matches"] for r in rt), "rows": rt}
    regress["evidence_class"] = regression.LABEL
    paths.write_json(_root(root, "reports", "regression-7b.json"), regress)
    return {"status": status, "gates": {k: g["passed"] for k, g in gates.items()}, "repeat_agreement": repeat,
            "invariance": invariance["identical"]}
