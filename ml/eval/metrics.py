"""Evaluation metrics. Standard library only.

Critical-event miss rate is the headline safety metric: the fraction of
sessions containing a true crisis or immediate-danger event that the system
failed to route to Critical. It is reported even when it is bad.
"""

from typing import Dict, List, Sequence, Tuple


def precision_recall_f1(tp: int, fp: int, fn: int) -> Dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def critical_event_miss_rate(pairs: Sequence[Tuple[bool, bool]]) -> Dict[str, float]:
    """pairs: (is_true_critical_event, was_routed_critical)."""
    positives = [p for p in pairs if p[0]]
    if not positives:
        return {"critical_events": 0, "missed": 0, "miss_rate": 0.0}
    missed = sum(1 for is_true, routed in positives if not routed)
    return {
        "critical_events": len(positives),
        "missed": missed,
        "miss_rate": round(missed / len(positives), 4),
    }


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


def percentile(values: List[float], p: float) -> float:
    """Nearest-rank percentile. p is 0-100."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(round(p / 100.0 * len(ordered) + 0.5))))
    return ordered[rank - 1]
