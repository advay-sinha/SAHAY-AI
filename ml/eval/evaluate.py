"""Corpus evaluation: labelled samples in, metrics out. Standard library only.

Every metric carries its denominator. Undefined metrics are None. Nothing is
averaged across slices to hide a weak one.
"""

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .metrics import binary_metrics, confusion, critical_event_miss_rate, ratio
from .predict import NOT_IMPLEMENTED, predict
from .schema import DETECTOR_CATEGORIES, LANGUAGES

SLICES = {
    "negation": "negated_risk_language",
    "quotation_attribution": "quoted_attributed_risk",
    "adversarial": "adversarial_injection",
}


def _detector_table(samples: Sequence[Mapping[str, Any]], preds: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    table: Dict[str, Any] = {}
    for cat in DETECTOR_CATEGORIES:
        if cat in NOT_IMPLEMENTED:
            positives = sum(1 for s in samples if s["labels"][cat])
            table[cat] = {"excluded": NOT_IMPLEMENTED[cat], "labelled_positives": positives}
            continue
        pairs = [(bool(s["labels"][cat]), bool(preds[s["id"]]["categories"][cat]["predicted"])) for s in samples]
        table[cat] = binary_metrics(confusion(pairs))
    return table


def _evidence(samples, preds) -> Dict[str, Any]:
    """Link validity (every cited id is a real victim turn, every positive cites
    one) and agreement with the labelled evidence on true positives."""
    cited_total = cited_valid = 0
    positives = positives_with_evidence = 0
    tp = tp_overlap = tp_exact = 0
    invalid: List[str] = []
    for s in samples:
        p = preds[s["id"]]
        valid_ids = set(p["victim_turn_ids"])
        for source, ids in p["cited_evidence"].items():
            for i in ids:
                cited_total += 1
                if i in valid_ids:
                    cited_valid += 1
                else:
                    invalid.append(f"{s['id']}:{source}:{i}")
        for cat, c in p["categories"].items():
            if not c["predicted"]:
                continue
            positives += 1
            if c["evidence"] and set(c["evidence"]) <= valid_ids:
                positives_with_evidence += 1
            else:
                invalid.append(f"{s['id']}:{cat}:no-valid-evidence")
            expected = set(s["expected_evidence"].get(cat) or [])
            if s["labels"][cat] and expected:
                tp += 1
                got = set(c["evidence"])
                tp_overlap += bool(got & expected)
                tp_exact += got == expected
    return {
        "cited_ids": cited_total, "cited_ids_valid": cited_valid,
        "cited_validity": ratio(cited_valid, cited_total),
        "positive_predictions": positives, "positives_with_valid_evidence": positives_with_evidence,
        "positive_evidence_validity": ratio(positives_with_evidence, positives),
        "true_positives_with_labels": tp,
        "evidence_overlap_rate": ratio(tp_overlap, tp),
        "evidence_exact_rate": ratio(tp_exact, tp),
        "invalid": invalid,
    }


def _routing(samples, preds) -> Dict[str, Any]:
    misses, escalations, precheck_misses, precheck_extra = [], [], [], []
    for s in samples:
        p, e = preds[s["id"]], s["expected"]
        if e["routed_critical"] and not p["routed_critical"]:
            misses.append({"id": s["id"], "language": s["language"], "tags": s["tags"],
                           "expected": "routed Critical", "actual": f"band={p['band']}, precheck={p['crisis_precheck']}",
                           "suppressed_turns": p["crisis_suppressed_turns"]})
        if not e["routed_critical"] and p["routed_critical"]:
            escalations.append({"id": s["id"], "language": s["language"], "tags": s["tags"],
                                "expected": "not routed Critical",
                                "actual": f"band={p['band']}, precheck={p['crisis_precheck']}"})
        if e["crisis_precheck"] and not p["crisis_precheck"]:
            precheck_misses.append(s["id"])
        if not e["crisis_precheck"] and p["crisis_precheck"]:
            precheck_extra.append(s["id"])
    pairs = [(s["expected"]["routed_critical"], preds[s["id"]]["routed_critical"]) for s in samples]
    return {
        "critical_routing": binary_metrics(confusion(pairs)),
        "critical_event_miss_rate": critical_event_miss_rate(pairs),
        "critical_misses": misses,
        "false_escalations": escalations,
        "crisis_precheck": binary_metrics(confusion(
            [(s["expected"]["crisis_precheck"], preds[s["id"]]["crisis_precheck"]) for s in samples])),
        "crisis_precheck_misses": precheck_misses,
        "crisis_precheck_unexpected_fires": precheck_extra,
    }


def _abstention(samples, preds) -> Dict[str, Any]:
    want = [s for s in samples if s["expected"]["abstain"] is True]
    dont = [s for s in samples if s["expected"]["abstain"] is False]
    got_want = [s["id"] for s in want if preds[s["id"]]["abstained"]]
    got_dont = [s["id"] for s in dont if not preds[s["id"]]["abstained"]]
    return {
        "expected_abstain": len(want), "abstained_when_expected": len(got_want),
        "abstention_coverage": ratio(len(got_want), len(want)),
        "missed_abstentions": sorted({s["id"] for s in want} - set(got_want)),
        "expected_score": len(dont), "scored_when_expected": len(got_dont),
        "score_coverage": ratio(len(got_dont), len(dont)),
        "unexpected_abstentions": sorted({s["id"] for s in dont} - set(got_dont)),
        "unspecified": len(samples) - len(want) - len(dont),
        "abstained_total": sum(1 for s in samples if preds[s["id"]]["abstained"]),
    }


def _bands(samples, preds) -> Dict[str, Any]:
    dist: Dict[str, int] = {}
    for s in samples:
        key = preds[s["id"]]["band"] or "Needs Human Assessment"
        dist[key] = dist.get(key, 0) + 1
    specified = [s for s in samples if s["expected"]["band"] is not None]
    agree = [s["id"] for s in specified if preds[s["id"]]["band"] == s["expected"]["band"]]
    return {
        "distribution": dict(sorted(dist.items())),
        "band_specified": len(specified), "band_agreement": len(agree),
        "band_agreement_rate": ratio(len(agree), len(specified)),
        "band_disagreements": [{"id": s["id"], "expected": s["expected"]["band"], "actual": preds[s["id"]]["band"]}
                               for s in specified if s["id"] not in agree],
    }


def _d4(samples, preds) -> Dict[str, Any]:
    """D4 must never be zero, must be structurally unavailable only on text."""
    problems = []
    for s in samples:
        p = preds[s["id"]]
        d4 = p["d4"] or {}
        if d4.get("score") is not None or d4.get("confidence") is not None:
            problems.append(f"{s['id']}: D4 has a value")
        unavailable = (p["normalization"] or {}).get("structurally_unavailable") or []
        text = s["channel"] in ("mobile_chat", "portal_chat")
        if text and unavailable != ["D4"]:
            problems.append(f"{s['id']}: text channel without D4 structural unavailability")
        if not text:
            if unavailable:
                problems.append(f"{s['id']}: audio channel was renormalised")
            if not p["abstained"] and p["band"] != "Critical":
                problems.append(f"{s['id']}: audio channel without acoustics produced a score")
    return {"checked": len(samples), "problems": problems}


def evaluate(samples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Evaluate a list of samples. Pure apart from calling the pipeline."""
    preds = {s["id"]: predict(s) for s in samples}
    by_lang = {lang: [s for s in samples if s["language"] == lang] for lang in LANGUAGES}
    slices = {name: [s for s in samples if s["labels"][label]] for name, label in SLICES.items()}
    return {
        "sample_count": len(samples),
        "language_counts": {k: len(v) for k, v in by_lang.items()},
        "detectors": _detector_table(samples, preds),
        "per_language": {lang: {"n": len(v), "detectors": _detector_table(v, preds), "routing": _routing(v, preds)}
                         for lang, v in by_lang.items()},
        "slices": {name: {"n": len(v), "routing": _routing(v, preds), "detectors": _detector_table(v, preds)}
                   for name, v in slices.items()},
        "routing": _routing(samples, preds),
        "evidence": _evidence(samples, preds),
        "abstention": _abstention(samples, preds),
        "bands": _bands(samples, preds),
        "d4": _d4(samples, preds),
        "predictions": {sid: {k: v for k, v in p.items() if k not in ("cited_evidence", "d4", "normalization")}
                        for sid, p in preds.items()},
    }


def headline(result: Mapping[str, Any]) -> Dict[str, Optional[Any]]:
    r = result["routing"]
    return {
        "samples": result["sample_count"],
        "critical_miss_count": len(r["critical_misses"]),
        "false_escalation_count": len(r["false_escalations"]),
        "critical_miss_rate": r["critical_event_miss_rate"]["miss_rate"],
        "critical_events": r["critical_event_miss_rate"]["critical_events"],
    }


def select(corpora: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [s for c in corpora for s in c["samples"]]
