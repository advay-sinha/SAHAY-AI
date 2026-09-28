"""Multi-turn shortcut check (plan M14): score 7b-v1 and 7b-v2 checkpoints on the 7b-v2 holdout.

    python -m ml.training.cli shortcut-check

The 7b-v2 holdout adds multi-turn records the 7b-v1 corpus never had: one positive turn plus one
negative, and two negatives. Scoring both generations of checkpoints on it, split by record kind,
answers two questions:

- does a model fire on harmless multi-turn records because they are multi-turn (the shortcut)?
  -> the false-alarm rate on all-negative records;
- can it handle mixed multi-turn records? -> macro F1 on one-positive records.

Inference only, aggregates only. Evidence class: synthetic development (agent-generated holdout).
Writes ``<SAHAY_TRAINING_ROOT>/stage-w-7b-v2/reports/shortcut-check.json``.
"""

from pathlib import Path
from typing import Any, Dict

from . import hardening as hx, metrics, paths, stage_w as sw, torchkit as tk

CHECKPOINTS = {
    "v1 W0 s13": "stage-w/checkpoints/W0-seed-13",
    "v1 W2 s13 (v1 selected)": "stage-w/checkpoints/W2-seed-13",
    "v2 W0 s13 (v2 selected)": "stage-w-7b-v2/checkpoints/W0-seed-13",
    "v2 W2 s13": "stage-w-7b-v2/checkpoints/W2-seed-13",
}
KINDS = ("single_turn", "combo_two_positive", "balanced_one_positive", "balanced_all_negative")
EVIDENCE = "synthetic_development (agent-generated 7b-v2 holdout; not independent)"


def record_kind(r: Any) -> str:
    if r["family"].startswith("combo2:"):
        return "balanced_" + r["lineage"]["kind"]
    return "combo_two_positive" if r["family"].startswith("combo:") else "single_turn"


def score(rows: Any, kinds: Any, fired: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in KINDS:
        idx = [i for i, kind in enumerate(kinds) if kind == k]
        s = metrics.summary([rows[i]["gold"] for i in idx], [fired[i] for i in idx], sw.DETECTOR_LABELS)
        negatives = [i for i in idx if not any(rows[i]["gold"].values())]
        out[k] = {"records": len(idx), "macro_f1": s["macro"]["f1"], "micro_f1": s["micro"]["f1"],
                  "all_negative_records": len(negatives),
                  "false_alarm_rate_on_all_negative": (round(sum(any(fired[i].values()) for i in negatives)
                                                             / len(negatives), 4) if negatives else None)}
    return out


def run(root: Path) -> Dict[str, Any]:
    records = hx.load_split(root, "synthetic_hardening_holdout", "7b-v2")
    rows = sw.fictional_rows(records)
    by_id = {r["id"]: record_kind(r) for r in records}
    kinds = [by_id[r["id"]] for r in rows]
    device = tk.device()
    n_det = len(sw.DETECTOR_LABELS)
    out: Dict[str, Any] = {"holdout": "7b-v2 synthetic_hardening_holdout", "records": len(rows),
                           "evidence_class": EVIDENCE, "results": {}}
    for name, rel in CHECKPOINTS.items():
        path = paths.confined(root, *rel.split("/"))
        if not path.is_dir():
            out["results"][name] = {"status": "checkpoint not found"}
            continue
        ck = sw.load_checkpoint(path, device)
        probs, _ = sw.predict(ck["net"], ck["tokenizer"], rows, device)
        fired = [metrics.firings(p[:n_det], sw.DETECTOR_LABELS) for p in probs]
        out["results"][name] = score(rows, kinds, fired)
        del ck
        tk.torch().cuda.empty_cache()
    paths.write_json(paths.confined(root, "stage-w-7b-v2", "reports", "shortcut-check.json"), out)
    return out
