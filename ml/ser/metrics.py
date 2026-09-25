"""Single-label SER metrics. Standard library only.

The headline metric is UAR (unweighted average recall = macro recall), the standard SER
measure under class imbalance. Undefined is never zero: a class with no gold examples has
recall ``None`` and is listed as excluded from the macro average. Every result states its
evidence class; nothing here is a clinical or production measurement.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

EVIDENCE_ACTED = "acted_corpus_actor_disjoint"
EVIDENCE_SEEN = "possibly_seen_in_pretraining"


def confusion(gold: Sequence[str], pred: Sequence[Optional[str]], classes: Sequence[str]) -> Dict[str, Dict[str, int]]:
    """gold class -> predicted class -> count. ``None`` predictions are counted as ``abstain``."""
    cols = list(classes) + ["abstain"]
    matrix = {g: {p: 0 for p in cols} for g in classes}
    for g, p in zip(gold, pred):
        if g not in matrix:
            raise ValueError("gold label outside the class list")
        matrix[g][p if p in classes else "abstain"] += 1
    return matrix


def _div(a: float, b: float) -> Optional[float]:
    return round(a / b, 4) if b else None


def evaluate(gold: Sequence[str], pred: Sequence[Optional[str]], classes: Sequence[str],
             evidence: str = EVIDENCE_ACTED) -> Dict[str, Any]:
    if len(gold) != len(pred):
        raise ValueError("gold and predictions differ in length")
    m = confusion(gold, pred, classes)
    per: Dict[str, Dict[str, Any]] = {}
    for c in classes:
        support = sum(m[c].values())
        tp = m[c][c]
        predicted = sum(m[g][c] for g in classes)
        recall, precision = _div(tp, support), _div(tp, predicted)
        f1 = None
        if support:
            f1 = 0.0 if not tp else round(2 * precision * recall / (precision + recall), 4)
        per[c] = {"support": support, "recall": recall, "precision": precision, "f1": f1}
    included = [c for c in classes if per[c]["recall"] is not None]
    n = len(gold)
    abstained = sum(m[g]["abstain"] for g in classes)
    return {
        "n": n,
        "uar": round(sum(per[c]["recall"] for c in included) / len(included), 4) if included else None,
        "macro_f1": round(sum(per[c]["f1"] for c in included) / len(included), 4) if included else None,
        "accuracy": _div(sum(m[c][c] for c in classes), n),
        "abstained": abstained,
        "classes_included": included,
        "classes_excluded_undefined": [c for c in classes if c not in included],
        "per_class": per,
        "min_class_recall": min((per[c]["recall"] for c in included), default=None),
        "confusion": m,
        "evidence_class": evidence,
    }


def by_group(gold: Sequence[str], pred: Sequence[Optional[str]], groups: Sequence[str], classes: Sequence[str],
             evidence: str = EVIDENCE_ACTED) -> Dict[str, Dict[str, Any]]:
    """UAR per group (for example sex or corpus), with the group size."""
    out: Dict[str, Dict[str, Any]] = {}
    for name in sorted(set(groups)):
        idx = [i for i, g in enumerate(groups) if g == name]
        r = evaluate([gold[i] for i in idx], [pred[i] for i in idx], classes, evidence)
        out[name] = {"n": r["n"], "uar": r["uar"], "macro_f1": r["macro_f1"], "min_class_recall": r["min_class_recall"]}
    return out


def argmax_label(probs: Sequence[float], classes: Sequence[str]) -> str:
    best = max(range(len(classes)), key=lambda i: (probs[i], -i))
    return classes[best]


def e2v_zero_shot(native_scores: Sequence[float], native_order: Sequence[str], affect_map: Mapping[str, Optional[str]],
                  classes: Sequence[str]) -> Dict[str, Any]:
    """emotion2vec+ zero-shot on the 5 affect classes.

    ``forced``: argmax over the five mapped classes only. ``abstaining``: argmax over all nine
    native classes; an unmapped winner (disgusted, surprised, other, <unk>) abstains.
    """
    affect_scores = {c: 0.0 for c in classes}
    for name, score in zip(native_order, native_scores):
        target = affect_map.get(name)
        if target is not None:
            affect_scores[target] += float(score)
    forced = argmax_label([affect_scores[c] for c in classes], classes)
    top = native_order[max(range(len(native_order)), key=lambda i: (native_scores[i], -i))]
    return {"forced": forced, "abstaining": affect_map.get(top), "affect_scores": affect_scores}


def selection_key(result: Mapping[str, Any]) -> tuple:
    """Higher UAR wins; ties go to the smaller model (fewer trainable parameters)."""
    return (result.get("uar") or 0.0, -(result.get("trainable_parameters") or 0))


def summarize(results: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: r.get(k) for k in ("model", "split", "uar", "macro_f1", "accuracy", "min_class_recall", "n",
                                   "evidence_class")} for r in results]
