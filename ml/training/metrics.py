"""Multi-label development metrics. Standard library only.

Every number computed here is *development evidence* on fictional or already-exposed data. It is
never an official, independent, clinical or production measurement, and callers must label it so.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

THRESHOLD = 0.5  # fixed, uncalibrated development threshold; never tuned on any split


def _div(a: float, b: float) -> Optional[float]:
    return round(a / b, 4) if b else None


def per_label(gold: Sequence[Mapping[str, bool]], pred: Sequence[Mapping[str, bool]],
              labels: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for name in labels:
        tp = fp = fn = tn = 0
        for g, p in zip(gold, pred):
            gv, pv = bool(g[name]), bool(p[name])
            tp += gv and pv
            fp += (not gv) and pv
            fn += gv and not pv
            tn += (not gv) and not pv
        precision, recall = _div(tp, tp + fp), _div(tp, tp + fn)
        f1 = (round(2 * precision * recall / (precision + recall), 4)
              if precision is not None and recall is not None and (precision + recall) else
              (0.0 if (tp + fn) else None))
        out[name] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "positives": tp + fn, "negatives": tn + fp,
                     "precision": precision, "recall": recall, "f1": f1, "specificity": _div(tn, tn + fp)}
    return out


def summary(gold: Sequence[Mapping[str, bool]], pred: Sequence[Mapping[str, bool]],
            labels: Sequence[str]) -> Dict[str, Any]:
    rows = per_label(gold, pred, labels)
    tp = sum(r["tp"] for r in rows.values())
    fp = sum(r["fp"] for r in rows.values())
    fn = sum(r["fn"] for r in rows.values())
    micro_p, micro_r = _div(tp, tp + fp), _div(tp, tp + fn)
    micro_f1 = (round(2 * micro_p * micro_r / (micro_p + micro_r), 4)
                if micro_p is not None and micro_r is not None and (micro_p + micro_r) else None)
    scored = [r for r in rows.values() if r["positives"]]
    macro = lambda k: round(sum(r[k] or 0.0 for r in scored) / len(scored), 4) if scored else None  # noqa: E731
    exact = sum(all(bool(g[n]) == bool(p[n]) for n in labels) for g, p in zip(gold, pred))
    wrong = sum(bool(g[n]) != bool(p[n]) for g, p in zip(gold, pred) for n in labels)
    recalls = [r["recall"] for r in scored if r["recall"] is not None]
    return {"records": len(gold), "micro": {"precision": micro_p, "recall": micro_r, "f1": micro_f1},
            "macro": {"precision": macro("precision"), "recall": macro("recall"), "f1": macro("f1")},
            "min_label_recall": min(recalls) if recalls else None,
            "exact_match": _div(exact, len(gold)), "hamming_loss": _div(wrong, len(gold) * len(labels)),
            "per_label": rows}


def firings(probabilities: Sequence[float], labels: Sequence[str], threshold: float = THRESHOLD) -> Dict[str, bool]:
    return {name: p >= threshold for name, p in zip(labels, probabilities)}


def selection_key(result: Mapping[str, Any]) -> tuple:
    """The predeclared Stage C rule, as a sort key where smaller wins:
    1. higher validation macro F1; 2. higher minimum per-label recall; 3. lower validation loss;
    4. lower numeric seed."""
    return (-(result["validation"]["macro"]["f1"] or 0.0), -(result["validation"]["min_label_recall"] or 0.0),
            result["validation_loss"], result["seed"])


def by_group(gold: Sequence[Mapping[str, bool]], pred: Sequence[Mapping[str, bool]], groups: Sequence[str],
             labels: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(groups)):
        idx: List[int] = [i for i, g in enumerate(groups) if g == key]
        s = summary([gold[i] for i in idx], [pred[i] for i in idx], labels)
        s.pop("per_label")
        out[key] = s
    return out
