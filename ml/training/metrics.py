"""Multi-label development metrics. Standard library only.

Every number computed here is *development evidence* on fictional or already-exposed data. It is
never an official, independent, clinical or production measurement, and callers must label it so.

Undefined is never zero. Each per-label metric carries its denominator: precision TP+FP, recall
TP+FN, specificity TN+FP. When a denominator is zero the metric is ``None`` with an explicit
reason. F1 is defined only when the label has positive support (TP+FN > 0). It is the harmonic mean
of precision and recall, and is exactly 0 when positives exist but none is found (TP = 0). A macro
average states the labels it includes and the labels it excludes as undefined.

``label_coverage`` reports positive and negative support per label, in frozen order. A metric set
without both kinds of support for every label is not fully evaluable for promotion.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

THRESHOLD = 0.5  # fixed, uncalibrated development threshold; never tuned on any split

NO_PREDICTED_POSITIVES = "undefined: no predicted positives (TP+FP = 0)"
NO_POSITIVE_SUPPORT = "undefined: no positive support (TP+FN = 0)"
NO_NEGATIVE_SUPPORT = "undefined: no negative support (TN+FP = 0)"


def _div(a: float, b: float) -> Optional[float]:
    return round(a / b, 4) if b else None


def label_metrics(tp: int, fp: int, fn: int, tn: int) -> Dict[str, Any]:
    """Per-label metrics from counts, with denominators and null reasons."""
    precision, recall, specificity = _div(tp, tp + fp), _div(tp, tp + fn), _div(tn, tn + fp)
    if tp + fn == 0:
        f1, f1_reason = None, NO_POSITIVE_SUPPORT
    elif precision is not None and recall is not None and (precision + recall):
        f1, f1_reason = round(2 * precision * recall / (precision + recall), 4), None
    else:
        f1, f1_reason = 0.0, None  # positives exist and TP = 0: F1 is exactly 0, not a filled-in value
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "positives": tp + fn, "negatives": tn + fp,
            "precision": precision, "recall": recall, "f1": f1, "specificity": specificity,
            "denominators": {"precision": tp + fp, "recall": tp + fn, "specificity": tn + fp},
            "undefined": {k: v for k, v in (("precision", None if precision is not None else NO_PREDICTED_POSITIVES),
                                            ("recall", None if recall is not None else NO_POSITIVE_SUPPORT),
                                            ("specificity", None if specificity is not None else NO_NEGATIVE_SUPPORT),
                                            ("f1", f1_reason)) if v},
            "f1_defined": f1 is not None}


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
        out[name] = label_metrics(tp, fp, fn, tn)
    return out


def macro(rows: Mapping[str, Mapping[str, Any]], labels: Sequence[str], metric: str) -> Dict[str, Any]:
    """A macro average over the labels where ``metric`` is defined, with the exact label sets."""
    included = [n for n in labels if rows[n][metric] is not None]
    value = round(sum(rows[n][metric] for n in included) / len(included), 4) if included else None
    return {"value": value, "labels_included": included, "defined_labels": len(included),
            "labels_excluded_undefined": [n for n in labels if rows[n][metric] is None], "of_labels": len(labels)}


def label_coverage(rows: Mapping[str, Mapping[str, Any]], labels: Sequence[str]) -> Dict[str, Any]:
    support = {n: {"positive": rows[n]["positives"], "negative": rows[n]["negatives"]} for n in labels}
    missing_pos = [n for n in labels if not rows[n]["positives"]]
    missing_neg = [n for n in labels if not rows[n]["negatives"]]
    full = not missing_pos and not missing_neg
    return {"labels": list(labels), "support": support, "labels_missing_positive_support": missing_pos,
            "labels_missing_negative_support": missing_neg, "full_label_coverage": full,
            "promotion_metrics_fully_evaluable": full}


def summary_from_rows(rows: Mapping[str, Mapping[str, Any]], labels: Sequence[str], records: int,
                      exact: Optional[int] = None, wrong: Optional[int] = None) -> Dict[str, Any]:
    tp = sum(rows[n]["tp"] for n in labels)
    fp = sum(rows[n]["fp"] for n in labels)
    fn = sum(rows[n]["fn"] for n in labels)
    micro_p, micro_r = _div(tp, tp + fp), _div(tp, tp + fn)
    micro_f1 = (round(2 * micro_p * micro_r / (micro_p + micro_r), 4)
                if micro_p is not None and micro_r is not None and (micro_p + micro_r) else None)
    m = {k: macro(rows, labels, k) for k in ("precision", "recall", "f1", "specificity")}
    recalls = [rows[n]["recall"] for n in labels if rows[n]["recall"] is not None]
    out: Dict[str, Any] = {
        "records": records, "micro": {"precision": micro_p, "recall": micro_r, "f1": micro_f1},
        "macro": {"precision": m["precision"]["value"], "recall": m["recall"]["value"], "f1": m["f1"]["value"],
                  "f1_labels_included": m["f1"]["labels_included"], "f1_defined_labels": m["f1"]["defined_labels"],
                  "f1_labels_excluded_undefined": m["f1"]["labels_excluded_undefined"]},
        "macro_detail": m, "min_label_recall": min(recalls) if recalls else None,
        "coverage": label_coverage(rows, labels), "per_label": dict(rows)}
    if exact is not None:
        out["exact_match"] = _div(exact, records)
    if wrong is not None:
        out["hamming_loss"] = _div(wrong, records * len(labels))
    return out


def summary(gold: Sequence[Mapping[str, bool]], pred: Sequence[Mapping[str, bool]],
            labels: Sequence[str]) -> Dict[str, Any]:
    rows = per_label(gold, pred, labels)
    exact = sum(all(bool(g[n]) == bool(p[n]) for n in labels) for g, p in zip(gold, pred))
    wrong = sum(bool(g[n]) != bool(p[n]) for g, p in zip(gold, pred) for n in labels)
    return summary_from_rows(rows, labels, len(gold), exact, wrong)


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
