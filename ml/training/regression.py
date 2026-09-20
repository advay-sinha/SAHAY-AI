"""Exposed regression comparison for the *already selected* shadow classifier.

Runs only after Stage C selection is final and never feeds back into training, early stopping,
thresholds, seed or checkpoint choice. It reads the exposed ``dev`` and ``candidates`` corpora and
the red-team ``victim_input`` cases. It never reads ``locked``, a blind corpus or a frozen corpus.

Every number here is **contaminated regression evidence**: these fixtures, their outcomes and
their known failures are published, and the fictional generator was screened against them. The
deterministic pipeline's own result on the same samples is reported alongside for comparison;
the deterministic pipeline remains the authority either way.
"""

import json
from typing import Any, Dict, List, Mapping, Sequence

from ..eval.predict import predict
from ..eval.schema import DETECTOR_CATEGORIES
from ..shadow.classifier import ShadowClassifier
from . import metrics, paths

CORPORA = ("dev.json", "candidates.json")
REDTEAM = "redteam.json"
FORBIDDEN = ("locked.json",)
LABEL = "contaminated exposed-regression evidence (published fixtures; not independent, blind, locked or official)"


def _load(name: str) -> Mapping[str, Any]:
    if name in FORBIDDEN:
        raise ValueError("the locked corpus is never evaluated")
    from ..eval.blind.leakage import CORPUS_DIR
    return json.loads((CORPUS_DIR / name).read_text(encoding="utf-8"))


def compare(samples: Sequence[Mapping[str, Any]], shadow: ShadowClassifier) -> Dict[str, Any]:
    labels = list(DETECTOR_CATEGORIES)
    gold, shadow_pred, det_pred, statuses = [], [], [], []
    for s in samples:
        det = predict(s)
        res = shadow.classify(s["turns"])
        statuses.append(res.status)
        if res.development_firings is None:
            continue
        gold.append({c: bool(s["labels"][c]) for c in labels})
        shadow_pred.append(dict(res.development_firings))
        det_pred.append({c: bool(v["predicted"]) if v["predicted"] is not None else False
                         for c, v in det["categories"].items()})
    shadow_summary = metrics.summary(gold, shadow_pred, labels) if gold else None
    det_labels = [c for c in labels if c != "explicit_human_request"]  # no deterministic text detector
    det_summary = metrics.summary(gold, det_pred, det_labels) if gold else None
    agree = {c: sum(sp[c] == dp[c] for sp, dp in zip(shadow_pred, det_pred)) for c in det_labels}
    return {"samples": len(samples), "scored": len(gold), "shadow_status": {k: statuses.count(k) for k in set(statuses)},
            "shadow": shadow_summary, "deterministic_same_samples": det_summary,
            "agreement_with_deterministic": agree, "evidence_class": LABEL}


def run(root: Any) -> Dict[str, Any]:
    shadow = ShadowClassifier(str(root))
    out: Dict[str, Any] = {"evidence_class": LABEL, "threshold": metrics.THRESHOLD, "never_evaluated": list(FORBIDDEN)}
    for name in CORPORA:
        out[name.replace(".json", "")] = compare(_load(name)["samples"], shadow)
    cases = [c for c in _load(REDTEAM)["cases"] if c["kind"] == "victim_input"]
    rows: List[Dict[str, Any]] = []
    for c in cases:
        res = shadow.classify([{"speaker": "victim", "text": c["text"]}])
        expected = c["expected"].get("crisis_precheck")
        fired = None if res.development_firings is None else res.development_firings["crisis_self_harm"]
        rows.append({"id": c["id"], "expected_crisis_precheck": expected, "shadow_crisis_firing": fired,
                     "matches": None if fired is None or expected is None else fired == expected})
    out["redteam_victim_input"] = {"cases": len(rows), "matches": sum(bool(r["matches"]) for r in rows),
                                   "rows": rows, "note": "assistant-output red-team cases test the output "
                                                         "guardrail, not victim text, so they are not scored"}
    shadow.unload()
    paths.write_json(paths.confined(root, "reports", "regression", "report.json"), out)
    return {k: (v if k != "redteam_victim_input" else {kk: vv for kk, vv in v.items() if kk != "rows"})
            for k, v in out.items()}
