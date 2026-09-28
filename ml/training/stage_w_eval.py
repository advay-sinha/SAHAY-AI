"""Stage W evaluation, run once after selection is final. Never feeds back into training or selection.

    python -m ml.training.cli stage-w-evaluate

Every trained run (all arms and seeds) is scored on four sets. Each result carries its evidence class:

1. ``synthetic_hardening_holdout``: the frozen Task 7B fictional holdout, eight detector labels,
   per language. Synthetic development evidence (agent-generated, not independent).
2. The weak test buckets (family-isolated from training), keyed by training target: the model's
   mapped logit against the source label, beside the deterministic rules on the same windows.
   Weak-supervision evidence: the labels are subreddit of origin, a hate-speech label and
   crowd-annotated stress, never SAHAY ground truth.
3. The exposed ``dev`` and ``candidates`` fixtures plus the red-team victim inputs: the model
   against the deterministic pipeline, with the fixture ids where only one of them is right.
   Contaminated exposed-regression evidence.
4. Indirect-wording probes written for this report: descriptive only, unreviewed.

It never reads ``locked.json`` or a blind corpus. The report holds ids and aggregates, never text.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..eval.blind.leakage import CORPUS_DIR
from ..eval.predict import predict as deterministic
from ..guardrails import crisis_check
from ..nlp.detectors import match_turn
from ..shadow import model as sm
from . import hardening as hx, metrics, paths, stage_w as sw, torchkit as tk
from .stage_c7b import evaluate_rows

FORBIDDEN = ("locked.json",)
EVIDENCE = {
    "holdout": "synthetic_development (agent-generated fictional holdout; not independent)",
    "weak": "weak_supervision_from_source_label (source labels, not SAHAY ground truth)",
    "exposed": "contaminated exposed-regression evidence (published fixtures; not independent, blind, locked or official)",
    "probes": "descriptive probe (written for this report; unreviewed)",
}
#: Weak training target -> the logit scored against it.
WEAK_HEAD = {"crisis_self_harm": "crisis_self_harm", "continuing_threat": "continuing_threat", "D5": sw.D5_HEAD}
#: Short fictional probes. ``indirect`` is the author's intent, not a reviewed label.
PROBES = (
    ("PW-EN-01", "en", True, "Everyone would be better off without me around."),
    ("PW-EN-02", "en", True, "I have been giving my things away, I won't need them much longer."),
    ("PW-EN-03", "en", True, "I just want to sleep and never wake up again."),
    ("PW-HG-01", "hinglish", True, "Sabko mere bina zyada sukoon milega."),
    ("PW-HG-02", "hinglish", True, "Ab aur nahi jhel sakti, bas so jaun aur kabhi na uthun."),
    ("PW-HI-01", "hi", True, "मेरे बिना सब खुश रहेंगे।"),
    ("PW-HI-02", "hi", True, "अब और नहीं सह सकती, बस सो जाऊँ और कभी न उठूँ।"),
    ("PW-EN-C1", "en", False, "I will not be here tomorrow because I am visiting my sister."),
    ("PW-HG-C1", "hinglish", False, "Kal main yahan nahi hoongi, mayke ja rahi hoon."),
    ("PW-HI-C1", "hi", False, "मैं कल यहाँ नहीं रहूँगी, बहन के घर जा रही हूँ।"),
)


def _load(name: str) -> Mapping[str, Any]:
    if name in FORBIDDEN:
        raise ValueError("the locked corpus is never evaluated")
    return json.loads((CORPUS_DIR / name).read_text(encoding="utf-8"))


def auroc(labels: Sequence[int], scores: Sequence[float]) -> Optional[float]:
    """Rank-based area under the ROC curve (ties get average ranks); None without both classes."""
    pos = sum(1 for y in labels if y)
    neg = len(labels) - pos
    if not pos or not neg:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    rank_sum = sum(r for r, y in zip(ranks, labels) if y)
    return round((rank_sum - pos * (pos + 1) / 2) / (pos * neg), 4)


def binary(labels: Sequence[int], fired: Sequence[bool]) -> Dict[str, Any]:
    tp = sum(1 for y, f in zip(labels, fired) if y and f)
    fp = sum(1 for y, f in zip(labels, fired) if not y and f)
    fn = sum(1 for y, f in zip(labels, fired) if y and not f)
    tn = sum(1 for y, f in zip(labels, fired) if not y and not f)
    return metrics.label_metrics(tp, fp, fn, tn)


def rules_fire(target: str, text: str) -> bool:
    """The deterministic signal for each weak training target (the ml/eval/predict.py mapping)."""
    if target == "crisis_self_harm":
        return bool(crisis_check(text)["crisis"])
    if target == "continuing_threat":
        d3 = match_turn("D3", text)
        return match_turn("D1", text) is not None or (d3 is not None and d3[0] >= 2)
    if target == "D5":
        return match_turn("D5", text) is not None
    raise ValueError(target)


def exposed_samples() -> Dict[str, List[Dict[str, Any]]]:
    out = {}
    for name in ("dev.json", "candidates.json"):
        out[name.replace(".json", "")] = [{"id": s["id"], "language": s["language"], "text": sm.model_text(s["turns"]),
                                           "gold": {c: bool(s["labels"][c]) for c in sw.DETECTOR_LABELS},
                                           "sample": s} for s in _load(name)["samples"]]
    out["redteam_victim_input"] = [
        {"id": c["id"], "language": c["language"], "text": c["text"], "expected_crisis": c["expected"].get("crisis_precheck")}
        for c in _load("redteam.json")["cases"] if c["kind"] == "victim_input"]
    return out


def deterministic_exposed(samples: Mapping[str, Sequence[Mapping[str, Any]]]) -> Dict[str, List[Dict[str, bool]]]:
    out: Dict[str, List[Dict[str, bool]]] = {}
    for corpus in ("dev", "candidates"):
        out[corpus] = []
        for s in samples[corpus]:
            cats = deterministic(s["sample"])["categories"]
            out[corpus].append({c: bool(cats[c]["predicted"]) if cats[c]["predicted"] is not None else False
                                for c in sw.DETECTOR_LABELS})
    out["redteam_victim_input"] = [{"crisis_self_harm": bool(crisis_check(s["text"])["crisis"])}
                                   for s in samples["redteam_victim_input"]]
    return out


def compare_exposed(samples: Sequence[Mapping[str, Any]], model: Sequence[Mapping[str, bool]],
                    rules: Sequence[Mapping[str, bool]]) -> Dict[str, Any]:
    labels = [c for c in sw.DETECTOR_LABELS if c != "explicit_human_request"]  # no deterministic text detector
    gold = [s["gold"] for s in samples]
    only_model, only_rules, model_false = [], [], []
    for s, mp, rp in zip(samples, model, rules):
        for c in labels:
            if s["gold"][c] and mp[c] and not rp[c]:
                only_model.append(f"{s['id']}:{c}")
            if s["gold"][c] and rp[c] and not mp[c]:
                only_rules.append(f"{s['id']}:{c}")
            if not s["gold"][c] and mp[c]:
                model_false.append(f"{s['id']}:{c}")
    ms, rs = metrics.summary(gold, model, labels), metrics.summary(gold, rules, labels)
    return {"samples": len(samples), "labels": labels,
            "model": {"micro_f1": ms["micro"]["f1"], "macro_f1": ms["macro"]["f1"],
                      "recall": {c: ms["per_label"][c]["recall"] for c in labels}},
            "rules": {"micro_f1": rs["micro"]["f1"], "macro_f1": rs["macro"]["f1"],
                      "recall": {c: rs["per_label"][c]["recall"] for c in labels}},
            "caught_by_model_only": only_model, "caught_by_rules_only": only_rules,
            "model_false_positives": model_false, "evidence_class": EVIDENCE["exposed"]}


def _strip(summary: Mapping[str, Any]) -> Dict[str, Any]:
    keep = ("records", "macro", "micro", "min_label_recall", "crisis_recall", "crisis_recall_by_language",
            "no_alert_specificity", "contrast", "errors", "coverage", "by_language")
    out = {k: summary[k] for k in keep if k in summary}
    out["per_label"] = {n: {k: summary["per_label"][n][k] for k in ("tp", "fp", "fn", "tn", "precision", "recall", "f1")}
                        for n in summary["per_label"]}
    return out


def evaluate_run(run: Mapping[str, Any], root: Path, data: Mapping[str, Any], device: str) -> Dict[str, Any]:
    ckpt = sw.load_checkpoint(paths.confined(root, *run["checkpoint"].split("/")), device)
    net, tok = ckpt["net"], ckpt["tokenizer"]
    n_det = len(sw.DETECTOR_LABELS)
    probs, _ = sw.predict(net, tok, data["holdout"], device)
    holdout = _strip(evaluate_rows(data["holdout"], [p[:n_det] for p in probs]))
    holdout["evidence_class"] = EVIDENCE["holdout"]
    weak: Dict[str, Any] = {}
    for source, rows in data["weak"].items():
        head = sw.LABELS.index(WEAK_HEAD[source])
        p, _ = sw.predict(net, tok, rows, device)
        scores = [x[head] for x in p]
        labels = [r["value"] for r in rows]
        weak[source] = {"target": WEAK_HEAD[source], "n": len(rows), "positives": sum(labels),
                        "model": {**{k: v for k, v in binary(labels, [s >= metrics.THRESHOLD for s in scores]).items()
                                     if k in ("tp", "fp", "fn", "tn", "precision", "recall", "f1", "specificity")},
                                  "auroc": auroc(labels, scores)},
                        "rules": data["weak_rules"][source], "evidence_class": EVIDENCE["weak"]}
    exposed: Dict[str, Any] = {}
    for corpus in ("dev", "candidates"):
        p, _ = sw.predict(net, tok, data["exposed"][corpus], device)
        fired = [metrics.firings(x[:n_det], sw.DETECTOR_LABELS) for x in p]
        exposed[corpus] = compare_exposed(data["exposed"][corpus], fired, data["exposed_rules"][corpus])
    rt = data["exposed"]["redteam_victim_input"]
    p, _ = sw.predict(net, tok, rt, device)
    crisis_i = sw.LABELS.index("crisis_self_harm")
    exposed["redteam_victim_input"] = {
        "cases": len(rt), "evidence_class": EVIDENCE["exposed"],
        "model_matches_expected": sum((x[crisis_i] >= metrics.THRESHOLD) == bool(s["expected_crisis"])
                                      for x, s in zip(p, rt) if s["expected_crisis"] is not None),
        "rules_match_expected": sum(r["crisis_self_harm"] == bool(s["expected_crisis"])
                                    for r, s in zip(data["exposed_rules"]["redteam_victim_input"], rt)
                                    if s["expected_crisis"] is not None)}
    p, _ = sw.predict(net, tok, data["probes"], device)
    probes = [{"id": pr["id"], "language": pr["language"], "indirect_by_author": pr["indirect"],
               "model_crisis_probability": round(x[crisis_i], 4), "model_fires": x[crisis_i] >= metrics.THRESHOLD,
               "model_d5_probability": round(x[sw.LABELS.index(sw.D5_HEAD)], 4),
               "crisis_precheck_fires": pr["rules"]} for pr, x in zip(data["probes"], p)]
    del net
    tk.torch().cuda.empty_cache()
    return {"arm": run["arm"], "seed": run["seed"], "selected_epoch": run["selected_epoch"], "holdout": holdout,
            "weak_test": weak, "exposed": exposed, "probes": {"rows": probes, "evidence_class": EVIDENCE["probes"]}}


def load_data(root: Path, limit: Optional[int] = None) -> Dict[str, Any]:
    holdout = sw.fictional_rows(hx.load_split(root, "synthetic_hardening_holdout"))
    weak = sw.load_weak(root, "test")
    if limit:
        holdout = holdout[:limit]
        weak = {s: r[:limit] for s, r in weak.items()}
    weak_rules = {}
    for source, rows in weak.items():
        labels = [r["value"] for r in rows]
        fired = [rules_fire(source, r["text"]) for r in rows]
        weak_rules[source] = {k: v for k, v in binary(labels, fired).items()
                              if k in ("tp", "fp", "fn", "tn", "precision", "recall", "f1", "specificity")}
    exposed = exposed_samples()
    probes = [{"id": i, "language": lang, "indirect": ind, "text": text, "rules": bool(crisis_check(text)["crisis"])}
              for i, lang, ind, text in PROBES]
    return {"holdout": holdout, "weak": weak, "weak_rules": weak_rules, "exposed": exposed,
            "exposed_rules": deterministic_exposed(exposed), "probes": probes}


def evaluate(root: Path, *, smoke: Optional[int] = None, log: Any = print) -> Dict[str, Any]:
    is_smoke = smoke is not None
    base = sw.SMOKE_ROOT if is_smoke else sw.ROOT
    runs = json.loads(paths.confined(root, *base, "reports", "runs.json").read_text(encoding="utf-8"))["runs"]
    selected = None
    if not is_smoke:
        selected = json.loads(paths.confined(root, *base, "checkpoints", "SELECTED.json").read_text(encoding="utf-8"))
    data = load_data(root, smoke)
    device = tk.device()
    results = []
    for run in runs:
        log(f"  evaluating {run['arm']} seed {run['seed']}")
        results.append(evaluate_run(run, root, data, device))
    report = {"model_id": sw.MODEL_ID, "threshold": metrics.THRESHOLD, "calibrated": False, "authoritative": False,
              "smoke": is_smoke, "selected": selected, "never_evaluated": list(FORBIDDEN), "evidence_classes": EVIDENCE,
              "weak_test_sizes": {s: len(r) for s, r in data["weak"].items()}, "runs": results}
    paths.write_json(paths.confined(root, *base, "reports", "evaluation.json"), report)
    return summary(report)


def summary(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Console summary: one line of headline numbers per run."""
    out = []
    for r in report["runs"]:
        out.append({"arm": r["arm"], "seed": r["seed"],
                    "holdout_macro_f1": r["holdout"]["macro"]["f1"],
                    "holdout_crisis_recall_by_language": r["holdout"].get("crisis_recall_by_language"),
                    "weak_auroc": {s: w["model"]["auroc"] for s, w in r["weak_test"].items()},
                    "weak_recall_model_vs_rules": {s: [w["model"]["recall"], w["rules"]["recall"]]
                                                   for s, w in r["weak_test"].items()},
                    "exposed_micro_f1_model_vs_rules": {c: [r["exposed"][c]["model"]["micro_f1"],
                                                            r["exposed"][c]["rules"]["micro_f1"]]
                                                        for c in ("dev", "candidates")},
                    "probes_fired": sum(p["model_fires"] for p in r["probes"]["rows"] if p["indirect_by_author"]),
                    "controls_fired": sum(p["model_fires"] for p in r["probes"]["rows"] if not p["indirect_by_author"])})
    return {"selected": report["selected"], "smoke": report["smoke"], "runs": out}
