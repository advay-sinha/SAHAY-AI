"""Evaluation metrics. Standard library only.

Undefined is not perfect. A metric whose denominator is zero is returned as
None together with its denominator, never silently as 0.0 or 1.0: "no
positives in this slice" and "recall 100%" must not look the same in a report.

Critical-event miss rate is the headline safety metric: the fraction of
samples containing a true crisis or immediate-danger event that the system
failed to route to Critical. It is reported even when it is bad.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def ratio(numerator: int, denominator: int) -> Optional[float]:
    """numerator / denominator, or None when the denominator is zero."""
    return round(numerator / denominator, 4) if denominator else None


def confusion(pairs: Iterable[Tuple[bool, bool]]) -> Dict[str, int]:
    """pairs: (expected, predicted) -> {tp, fp, tn, fn, n}."""
    c = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for expected, predicted in pairs:
        if expected and predicted:
            c["tp"] += 1
        elif expected:
            c["fn"] += 1
        elif predicted:
            c["fp"] += 1
        else:
            c["tn"] += 1
    c["n"] = c["tp"] + c["fp"] + c["tn"] + c["fn"]
    return c


def binary_metrics(c: Dict[str, int]) -> Dict[str, Any]:
    """Precision, recall, F1 and specificity with explicit denominators.

    F1 is None unless both precision and recall are defined. When both are
    defined and both are zero, F1 is 0.0 (a real, bad result).
    """
    precision = ratio(c["tp"], c["tp"] + c["fp"])
    recall = ratio(c["tp"], c["tp"] + c["fn"])
    specificity = ratio(c["tn"], c["tn"] + c["fp"])
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = round(2 * precision * recall / (precision + recall), 4)
    return {
        **c,
        "precision": precision, "precision_denominator": c["tp"] + c["fp"],
        "recall": recall, "recall_denominator": c["tp"] + c["fn"],
        "specificity": specificity, "specificity_denominator": c["tn"] + c["fp"],
        "f1": f1,
    }


def precision_recall_f1(tp: int, fp: int, fn: int) -> Dict[str, Optional[float]]:
    """Earlier interface, kept; undefined values are now None, not 0.0."""
    m = binary_metrics({"tp": tp, "fp": fp, "tn": 0, "fn": fn, "n": tp + fp + fn})
    return {"precision": m["precision"], "recall": m["recall"], "f1": m["f1"]}


def critical_event_miss_rate(pairs: Sequence[Tuple[bool, bool]]) -> Dict[str, Any]:
    """pairs: (is_true_critical_event, was_routed_critical).

    With no critical events the miss rate is undefined (None), not 0.0.
    """
    positives = [p for p in pairs if p[0]]
    missed = sum(1 for _is_true, routed in positives if not routed)
    return {"critical_events": len(positives), "missed": missed, "miss_rate": ratio(missed, len(positives))}


def fmt(value: Optional[float]) -> str:
    """Human-readable metric: 'n/a' for undefined, never a fake number."""
    return "n/a" if value is None else f"{value:.3f}"


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate by Levenshtein distance over word tokens."""
    ref = reference.split()
    hyp = hypothesis.split()
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        current = [i]
        for j, h in enumerate(hyp, start=1):
            cost = 0 if r == h else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return round(previous[-1] / len(ref), 4)


def percentile(values: List[float], p: float) -> Optional[float]:
    """Nearest-rank percentile. p is 0-100. None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(round(p / 100.0 * len(ordered) + 0.5))))
    return ordered[rank - 1]
