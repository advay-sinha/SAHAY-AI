"""Task 7B step 1: ID-only error analysis of the Task 7 selected shadow checkpoint.

    python -m ml.training.cli error-analysis

Scores the Task 7 checkpoint on the Task 7 fictional validation and synthetic development-test
splits, the exposed dev and candidate fixtures and the red-team victim-input cases, then files every
error into a failure family. The private report holds, per erroneous record, only: ID, language,
script, expected and predicted labels, template-family ID, challenge slices and the FN/FP family.
It never holds or prints text. Aggregate tokenisation statistics (token counts, 128-token
truncation) are computed with the checkpoint's own tokenizer.

After this analysis the Task 7 fictional validation and test splits are **exposed development
material**, not fresh holdouts; the Task 7B holdout is generated separately and frozen first.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from ..eval.schema import DETECTOR_CATEGORIES
from ..shadow import model as sm
from ..shadow.classifier import ShadowClassifier
from . import fictional, paths

LABELS = tuple(DETECTOR_CATEGORIES)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")

FAMILIES = (
    "indirect crisis wording", "desire to disappear or not remain alive", "temporal ambiguity",
    "clause-scoped negation", "quoted speech", "attributed speech", "historical crisis statements",
    "third-person crisis discussion", "code-switched crisis wording", "Hindi spelling and Unicode variation",
    "romanized Hindi spelling variation", "legal help versus legal urgency", "generic legal discussion",
    "coercion versus ordinary disagreement", "controlling behavior without explicit threat",
    "explicit human-help requests", "multi-label overlap", "truncation/tokenization failures", "other")
#: Task 7 templates whose crisis wording is a wish to disappear or not remain alive.
DISAPPEAR_TEMPLATES = {"c01", "c05", "c07"}


def script_of(text: str) -> str:
    dev, lat = bool(_DEVANAGARI.search(text)), bool(_LATIN.search(text))
    return "mixed" if dev and lat else "devanagari" if dev else "latin" if lat else "none"


def families_for(label: str, kind: str, language: str, slices: Sequence[str], templates: Sequence[str],
                 truncated: bool, positives: int) -> List[str]:
    """Failure families for one FN or FP on one label. Deterministic, rule-based, text-free."""
    s = set(slices)
    out: List[str] = []
    if truncated:
        out.append("truncation/tokenization failures")
    if positives > 1:
        out.append("multi-label overlap")
    if label == "crisis_self_harm":
        if kind == "FN":
            if s & {"indirect", "weak_indicators"}:
                out.append("indirect crisis wording")
            if set(templates) & DISAPPEAR_TEMPLATES:
                out.append("desire to disappear or not remain alive")
            if "conditional" in s:
                out.append("temporal ambiguity")
            if s & {"code_switching", "code_switch"} or language == "hinglish":
                out.append("code-switched crisis wording")
        else:
            out += [f for tag, f in (("negation", "clause-scoped negation"), ("negated_crisis", "clause-scoped negation"),
                                     ("quotation", "quoted speech"), ("quoted_crisis", "quoted speech"),
                                     ("attribution", "attributed speech"), ("historical", "historical crisis statements"))
                    if tag in s]
            if "attribution" in s:
                out.append("third-person crisis discussion")
    elif label == "legal_urgency":
        out.append("legal help versus legal urgency" if kind == "FN" else "generic legal discussion")
    elif label == "communication_safety_coercion":
        out.append("controlling behavior without explicit threat" if kind == "FN"
                   else "coercion versus ordinary disagreement")
    elif label == "explicit_human_request":
        out.append("explicit human-help requests")
    if "unicode_variant" in s and language == "hi":
        out.append("Hindi spelling and Unicode variation")
    if s & {"misspelling", "regional_variant"} and language == "hinglish":
        out.append("romanized Hindi spelling variation")
    return sorted(set(out)) or ["other"]


def _rows(shadow: ShadowClassifier, tok: Any, items: Sequence[Mapping[str, Any]], source: str) -> List[Dict[str, Any]]:
    rows = []
    for it in items:
        text = sm.model_text(it["turns"])
        n_tokens = len(tok(text, truncation=False)["input_ids"]) if text else 0
        res = shadow.classify(it["turns"])
        fired = res.development_firings or {}
        expected = [c for c in LABELS if it["labels"].get(c)]
        predicted = [c for c in LABELS if fired.get(c)]
        errors = []
        for c in LABELS:
            if c not in it["labels"]:
                continue  # red-team victim-input cases carry only an expected crisis outcome
            gold, pred = bool(it["labels"].get(c)), bool(fired.get(c))
            if gold != pred:
                kind = "FN" if gold else "FP"
                errors.append({"label": c, "kind": kind,
                               "families": families_for(c, kind, it["language"], it["slices"], it.get("templates", []),
                                                        n_tokens > sm.MAX_LEN, len(expected))})
        rows.append({"id": it["id"], "source": source, "language": it["language"],
                     "script": script_of(text), "expected": expected, "predicted": predicted,
                     "template_family": it.get("family"), "slices": sorted(it["slices"]), "tokens": n_tokens,
                     "truncated": n_tokens > sm.MAX_LEN, "errors": errors, "status": res.status})
    return rows


def _fixtures(name: str) -> List[Dict[str, Any]]:
    from ..eval.blind.leakage import CORPUS_DIR
    data = json.loads((CORPUS_DIR / name).read_text(encoding="utf-8"))
    if name.startswith("redteam"):
        return [{"id": c["id"], "language": c["language"], "turns": [{"speaker": "victim", "text": c["text"]}],
                 "labels": {"crisis_self_harm": bool(c["expected"].get("crisis_precheck"))}, "slices": [c["category"]]}
                for c in data["cases"] if c["kind"] == "victim_input"]
    return [{"id": s["id"], "language": s["language"], "turns": s["turns"], "labels": s["labels"],
             "slices": s.get("tags", [])} for s in data["samples"]]


def run(root: Path) -> Dict[str, Any]:
    from . import torchkit as tk
    shadow = ShadowClassifier(str(root))
    state = shadow.load()
    if state.status != "loaded":
        raise RuntimeError(f"Task 7 checkpoint unavailable: {state.reason}")
    pointer = json.loads(paths.confined(root, "checkpoints", "stage-c", "SELECTED.json").read_text(encoding="utf-8"))
    tok = tk.load_tokenizer(paths.confined(root, *pointer["checkpoint"].split("/"), sm.ENCODER_DIR))
    records = fictional.load(root)
    items: Dict[str, List[Dict[str, Any]]] = {}
    for split in ("validation", "synthetic_development_test"):
        items[f"task7_{split}"] = [{"id": r["id"], "language": r["language"], "turns": r["turns"], "labels": r["labels"],
                                   "slices": r["phenomena"], "templates": r["templates"], "family": r["family"]}
                                  for r in records if r["split"] == split]
    items["dev"] = _fixtures("dev.json")
    items["candidates"] = _fixtures("candidates.json")
    items["redteam_victim_input"] = _fixtures("redteam.json")
    rows = [row for source, its in items.items() for row in _rows(shadow, tok, its, source)]
    shadow.unload()

    family_counts: Dict[str, Counter] = defaultdict(Counter)
    label_counts: Dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        for e in row["errors"]:
            if row["source"] == "redteam_victim_input" and e["label"] != "crisis_self_harm":
                continue
            label_counts[row["source"]][f"{e['label']}:{e['kind']}"] += 1
            for f in e["families"]:
                family_counts[row["source"]][f] += 1
    tokens = [r["tokens"] for r in rows]
    tokenisation = {"records": len(rows), "mean_tokens": round(sum(tokens) / max(1, len(tokens)), 1),
                    "max_tokens": max(tokens) if tokens else 0,
                    "truncated_at_128": sum(r["truncated"] for r in rows),
                    "by_script": dict(Counter(r["script"] for r in rows))}
    report = {"checkpoint": {"run": pointer.get("run"), "seed": pointer.get("seed"), "task": "7"},
              "sources": {k: len(v) for k, v in items.items()}, "families": {k: dict(v) for k, v in family_counts.items()},
              "errors_by_label": {k: dict(v) for k, v in label_counts.items()}, "tokenisation": tokenisation,
              "rows": [r for r in rows if r["errors"]],
              "exposure_note": "Task 7 fictional validation and synthetic_development_test are exposed development "
                               "material after this analysis; failed exposed fixtures are never copied or "
                               "paraphrased into new training records"}
    paths.write_json(paths.confined(root, "task7b", "reports", "error-analysis.json"), report)
    return {k: v for k, v in report.items() if k != "rows"} | {"erroneous_records": len(report["rows"])}
