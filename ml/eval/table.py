"""Evaluation table (plan step M14): every measured number in one place, each with its source.

It assembles one table from files that already exist:

- a deterministic evaluation JSON written by ``python -m ml.eval.run_eval`` (HANDOVER metrics M1, M5, M7,
  and the abstention and band checks);
- the private speech-emotion and text-affect run reports beneath ``SAHAY_TRAINING_ROOT``, when that
  variable is set, with a clip- or sentence-level bootstrap interval recomputed from each run's
  prediction file.

Rules it enforces:

- A number that was not measured is ``pending``, never zero.
- Every row carries an evidence class and a source path. Exposed fixtures are labelled as exposed.
- Nothing is called "official" unless the locked set has samples.
- Output holds aggregates only: no fixture text, no utterances, no dataset row identifiers.
- The rendered text passes a wording guard (no clinical or production claims).

Standard library only. It never loads a model and never opens the network.

    python -m ml.eval.table --eval-json runtime/eval/eval-all.json --out runtime/eval
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

TABLE_VERSION = "eval-table-1.0"
#: Class order of every affect prediction file (ml/ser and ml/textaffect; a test keeps them equal).
AFFECT_CLASSES = ("neutral", "happy", "sad", "angry", "fearful")
STATUSES = ("measured", "pending", "test_enforced", "unvalidated", "not_available")
EVAL_EVIDENCE = {
    "dev": "exposed_development",
    "candidate": "exposed_candidate",
    "locked": "locked",
}
DEFAULT_RESAMPLES = 1000
DEFAULT_SEED = 13

#: Phrases that must never appear in the rendered table. Case-insensitive.
BANNED_PHRASES = (
    "clinically validated", "clinically proven", "clinical accuracy", "production accuracy",
    "production ready", "production-ready", "state of the art", "state-of-the-art", "diagnostic accuracy",
    "guaranteed",
)
#: Keys that would carry row-level content; none may appear anywhere in the output.
ROW_LEVEL_KEYS = ("text", "utterance", "transcript", "turns", "predictions", "clip_id", "evidence_quotes")


class WordingError(ValueError):
    """The rendered table contains a claim the project does not make."""


# --------------------------------------------------------------------------- statistics

def wilson(k: int, n: int, z: float = 1.96) -> Optional[Tuple[float, float]]:
    """95% Wilson score interval for k successes out of n; None when n is 0."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def uar(gold: Sequence[str], pred: Sequence[str]) -> Optional[float]:
    """Unweighted average recall over the classes present in ``gold``."""
    support: Dict[str, int] = {}
    hit: Dict[str, int] = {}
    for g, p in zip(gold, pred):
        support[g] = support.get(g, 0) + 1
        if g == p:
            hit[g] = hit.get(g, 0) + 1
    if not support:
        return None
    return sum(hit.get(c, 0) / s for c, s in support.items()) / len(support)


def bootstrap_uar(gold: Sequence[str], pred: Sequence[str], resamples: int, seed: int) -> Optional[Tuple[float, float]]:
    """Percentile 95% interval of UAR over item-level resamples (ignores speaker clustering)."""
    n = len(gold)
    if n == 0 or resamples <= 0:
        return None
    rng = random.Random(seed)
    values: List[float] = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        v = uar([gold[i] for i in idx], [pred[i] for i in idx])
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    lo = values[int(0.025 * (len(values) - 1))]
    hi = values[int(math.ceil(0.975 * (len(values) - 1)))]
    return (round(lo, 4), round(hi, 4))


def argmax(probs: Sequence[float]) -> str:
    best = max(range(len(probs)), key=lambda i: probs[i])
    return AFFECT_CLASSES[best]


# --------------------------------------------------------------------------- rows

def row(metric_id: str, metric: str, *, scope: str, status: str, evidence_class: str, source: str,
        value: Optional[float] = None, ci: Optional[Tuple[float, float]] = None, n: Optional[int] = None,
        note: str = "") -> Dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    if status == "measured" and value is None:
        raise ValueError(f"{metric_id}: a measured row needs a value")
    if status != "measured" and value is not None:
        raise ValueError(f"{metric_id}: only a measured row carries a value")
    return {
        "metric_id": metric_id, "metric": metric, "scope": scope, "value": value,
        "ci95": list(ci) if ci else None, "n": n, "evidence_class": evidence_class,
        "source": source, "status": status, "note": note,
    }


def _rate_row(metric_id: str, metric: str, scope: str, block: Mapping[str, Any], key: str, evidence: str,
              source: str, note: str = "") -> Dict[str, Any]:
    """A precision or recall row from an evaluate() confusion block, with a Wilson interval."""
    denom = block.get(f"{key}_denominator") or 0
    if not denom or block.get(key) is None:
        return row(metric_id, metric, scope=scope, status="pending", evidence_class=evidence, source=source,
                   n=denom, note=(note + "; " if note else "") + "no positives in this split")
    k = block["tp"] if key in ("recall", "precision") else block["tn"]
    return row(metric_id, metric, scope=scope, status="measured", evidence_class=evidence, source=source,
               value=round(block[key], 4), ci=wilson(k, denom), n=denom, note=note)


def eval_rows(report: Mapping[str, Any], source: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    splits = report.get("splits", {})
    locked = report.get("official_locked_metrics", {}) or {}
    locked_n = int(locked.get("locked_samples") or 0)

    for split in ("dev", "candidate", "locked"):
        result = (splits.get(split) or {}).get("result")
        evidence = EVAL_EVIDENCE[split]
        if split == "locked" and (not result or locked_n == 0):
            rows.append(row("M1", "Critical-event miss rate", scope="locked", status="pending",
                            evidence_class="locked", source=source, n=0,
                            note=f"locked set has {locked_n} samples; crisis and danger samples need two reviewer approvals"))
            continue
        if not result:
            continue
        rt = result["routing"]
        miss = rt["critical_event_miss_rate"]
        events, missed = int(miss["critical_events"]), int(miss["missed"])
        if events:
            rows.append(row("M1", "Critical-event miss rate", scope=split, status="measured", evidence_class=evidence,
                            source=source, value=round(missed / events, 4), ci=wilson(missed, events), n=events,
                            note=f"{missed} of {events} critical events missed"))
        else:
            rows.append(row("M1", "Critical-event miss rate", scope=split, status="pending", evidence_class=evidence,
                            source=source, n=0, note="no critical events in this split"))
        rows.append(_rate_row("M1a", "Critical routing recall", split, rt["critical_routing"], "recall", evidence, source))
        rows.append(_rate_row("M1b", "Critical routing precision", split, rt["critical_routing"], "precision",
                              evidence, source, note=f"{len(rt.get('false_escalations', []))} false escalations"))
        rows.append(_rate_row("M1c", "Crisis pre-check recall", split, rt["crisis_precheck"], "recall", evidence, source))
        rows.append(_rate_row("M1d", "Crisis pre-check precision", split, rt["crisis_precheck"], "precision",
                              evidence, source))
        for category in sorted(result.get("detectors", {})):
            block = result["detectors"][category]
            rows.append(_rate_row("M7", f"Detector recall: {category}", split, block, "recall", evidence, source))
            rows.append(_rate_row("M7", f"Detector precision: {category}", split, block, "precision", evidence, source))
        ab = result.get("abstention", {})
        if ab.get("expected_abstain"):
            k = int(ab["abstained_when_expected"])
            rows.append(row("A1", "Abstains when abstention is expected", scope=split, status="measured",
                            evidence_class=evidence, source=source, value=round(k / ab["expected_abstain"], 4),
                            ci=wilson(k, int(ab["expected_abstain"])), n=int(ab["expected_abstain"])))
        bands = result.get("bands", {})
        if bands.get("band_specified"):
            k, n = int(bands["band_agreement"]), int(bands["band_specified"])
            rows.append(row("A2", "Band agreement with the labelled band", scope=split, status="measured",
                            evidence_class=evidence, source=source, value=round(k / n, 4), ci=wilson(k, n), n=n))

    rt = report.get("redteam")
    if rt and rt.get("cases"):
        cases, passed = int(rt["cases"]), int(rt["passed"])
        sev = rt.get("failures_by_severity", {})
        rows.append(row("M5", "Red-team cases blocked before synthesis", scope="redteam", status="measured",
                        evidence_class="exposed_redteam", source=source, value=round(passed / cases, 4),
                        ci=wilson(passed, cases), n=cases,
                        note="critical failures " + str(sev.get("critical", 0)) + "; fixtures exposed on 2026-09-11"))
    else:
        rows.append(row("M5", "Red-team cases blocked before synthesis", scope="redteam", status="pending",
                        evidence_class="exposed_redteam", source=source))
    return rows


def static_rows() -> List[Dict[str, Any]]:
    """Metrics with no measurement yet, and those enforced by tests rather than measured."""
    handover = "docs/HANDOVER.md"
    return [
        row("M2", "Turn latency p50 / p95 (victim stops to assistant starts)", scope="voice turn", status="pending",
            evidence_class="none", source=handover,
            note="the turn loop is not instrumented end to end; speech-to-text smoke timings are not M2"),
        row("M3", "Time to first safety alert on the console", scope="end to end", status="pending",
            evidence_class="none", source=handover, note="needs scripted end-to-end runs"),
        row("M4", "Executive decision time on the packet", scope="rehearsal", status="pending",
            evidence_class="none", source=handover, note="needs a rehearsal with a non-team reader"),
        row("M6", "Speech-to-text word error rate by language and condition", scope="hi, en", status="pending",
            evidence_class="none", source=handover, note="no target claimed; needs the approved evaluation audio"),
        row("M8", "Assessment data reaching the victim client", scope="backend payloads", status="test_enforced",
            evidence_class="automated_test",
            source="backend/tests/test_role_fanout.py; backend/tests/test_timeline_leakage.py",
            note="enforced by tests on every run; not a sampled measurement"),
        row("M9", "Repeat-question rate per session", scope="scenario transcripts", status="pending",
            evidence_class="none", source=handover),
        row("D4", "Voice prosody rule (D4) agreement with human judgement", scope="voice turns",
            status="unvalidated", evidence_class="none", source="ml/acoustics/D4_CARD.md",
            note="rule is unit-tested only; needs team recordings and expert review"),
    ]


# --------------------------------------------------------------------------- private run reports

def _read_jsonl(path: Path) -> Iterable[Mapping[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _ci_if_consistent(gold: List[str], pred: List[str], reported: Optional[float], resamples: int,
                      seed: int) -> Tuple[Optional[Tuple[float, float]], str]:
    """Interval only when the prediction file reproduces the reported UAR; otherwise explain why not."""
    if not gold:
        return None, "no prediction rows for this scope"
    recomputed = uar(gold, pred)
    if reported is None or recomputed is None or abs(recomputed - reported) > 0.001:
        return None, "prediction file does not reproduce the reported value; interval omitted"
    return bootstrap_uar(gold, pred, resamples, seed), ""


def ser_rows(root: Path, resamples: int, seed: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    runs = root / "ser" / "runs"
    for report_path in sorted(runs.glob("*/report.json")):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        run = report_path.parent.name
        for variant, body in sorted(report.get("variants", {}).items()):
            preds_path = report_path.parent / f"predictions-{variant}.jsonl"
            preds = list(_read_jsonl(preds_path)) if preds_path.is_file() else []
            for scope, s in sorted(body.get("scores", {}).items()):
                if not (scope.startswith("test:") or scope.startswith("cross:")) or s.get("uar") is None:
                    continue
                kind, dataset = scope.split(":", 1)
                picked = [p for p in preds if p.get("dataset") == dataset and (kind == "cross" or p.get("split") == "test")]
                ci, why = (_ci_if_consistent([p["gold"] for p in picked], [argmax(p["probs"]) for p in picked],
                                             s["uar"], resamples, seed) if preds else (None, "no prediction file"))
                note = f"macro-F1 {s.get('macro_f1')}; lowest class recall {s.get('min_class_recall')}"
                rows.append(row("SER", f"Speech emotion UAR: {run}/{variant}", scope=scope, status="measured",
                                evidence_class=s.get("evidence_class", "unlabelled"),
                                source=f"SAHAY_TRAINING_ROOT/ser/runs/{run}/report.json", value=round(s["uar"], 4),
                                ci=ci, n=s.get("n"), note="; ".join(x for x in (note, why) if x)))
    return rows


def text_rows(root: Path, resamples: int, seed: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    runs = root / "textaffect" / "runs-v2"
    for report_path in sorted(runs.glob("*/report.json")):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        run = report_path.parent.name
        preds_path = report_path.parent / "predictions.jsonl"
        preds = list(_read_jsonl(preds_path)) if preds_path.is_file() else []
        for scope, s in sorted(report.get("scores", {}).items()):
            if not scope.startswith("test:") or s.get("uar") is None:
                continue
            language = scope.split(":", 1)[1]
            picked = [p for p in preds if p.get("split") == "test" and p.get("language") == language]
            if picked:
                ci, why = _ci_if_consistent([p["gold"] for p in picked], [argmax(p["probs"]) for p in picked],
                                            s["uar"], resamples, seed)
            else:
                ci, why = None, "subset not identifiable in the prediction file; interval omitted"
            note = f"macro-F1 {s.get('macro_f1')}; lowest class recall {s.get('min_class_recall')}"
            rows.append(row("TXT", f"Text affect UAR: {run}", scope=scope, status="measured",
                            evidence_class=s.get("evidence_class", "unlabelled"),
                            source=f"SAHAY_TRAINING_ROOT/textaffect/runs-v2/{run}/report.json",
                            value=round(s["uar"], 4), ci=ci, n=s.get("n"),
                            note="; ".join(x for x in (note, why) if x)))
    return rows


def stage_w_rows(root: Path) -> List[Dict[str, Any]]:
    """The selected Stage W checkpoint (shadow MuRIL, weak supervision): headline rows by evidence class."""
    path = root / "stage-w" / "reports" / "evaluation.json"
    source = "SAHAY_TRAINING_ROOT/stage-w/reports/evaluation.json"
    if not path.is_file():
        return [row("SHD", "Shadow safety detector (Stage W)", scope="all", status="not_available",
                    evidence_class="none", source=source, note="no Stage W evaluation report found")]
    report = json.loads(path.read_text(encoding="utf-8"))
    sel = report.get("selected") or {}
    run = next((r for r in report["runs"] if r["arm"] == sel.get("arm") and r["seed"] == sel.get("seed")), None)
    if run is None:
        return [row("SHD", "Shadow safety detector (Stage W)", scope="all", status="not_available",
                    evidence_class="none", source=source, note="no selected run in the report")]
    tag = f"{run['arm']} seed {run['seed']}"
    out: List[Dict[str, Any]] = []
    h = run["holdout"]
    out.append(row("SHD", f"Shadow detector macro F1, fictional holdout ({tag})", scope="synthetic holdout",
                   status="measured", evidence_class="synthetic_development", source=source,
                   value=h["macro"]["f1"], n=h.get("records"),
                   note="labels without positive support excluded: "
                        + (", ".join(h["macro"].get("f1_labels_excluded_undefined") or []) or "none")))
    for lang, rec in sorted((h.get("crisis_recall_by_language") or {}).items()):
        if rec is not None:
            out.append(row("SHD", f"Shadow detector crisis recall, fictional holdout ({tag})", scope=lang,
                           status="measured", evidence_class="synthetic_development", source=source, value=rec))
    for target, w in sorted(run["weak_test"].items()):
        m, r = w["model"], w["rules"]
        k, n = m["tp"], m["tp"] + m["fn"]
        out.append(row("SHD", f"Shadow detector recall vs source label: {target} ({tag})", scope="weak test bucket",
                       status="measured", evidence_class="weak_supervision_from_source_label", source=source,
                       value=m["recall"], ci=wilson(k, n), n=n,
                       note=f"AUROC {m.get('auroc')}; precision {m['precision']}; deterministic rules recall "
                            f"{r['recall']}, precision {r['precision']}"))
    for corpus in ("dev", "candidates"):
        e = run["exposed"][corpus]
        out.append(row("SHD", f"Shadow detector micro F1 vs deterministic rules ({tag})", scope=corpus,
                       status="measured", evidence_class=EVAL_EVIDENCE.get(corpus if corpus == "dev" else "candidate"),
                       source=source, value=e["model"]["micro_f1"], n=e["samples"],
                       note=f"rules micro F1 {e['rules']['micro_f1']}; caught by the model only "
                            f"{len(e['caught_by_model_only'])}; model false positives {len(e['model_false_positives'])}"))
    probes = run["probes"]["rows"]
    ind = [p for p in probes if p["indirect_by_author"]]
    ctl = [p for p in probes if not p["indirect_by_author"]]
    out.append(row("SHD", f"Shadow detector fires on indirect-wording probes ({tag})", scope="10 probes",
                   status="measured", evidence_class="descriptive_probe", source=source,
                   value=round(sum(p["model_fires"] for p in ind) / len(ind), 4), n=len(ind),
                   note=f"non-crisis controls fired {sum(p['model_fires'] for p in ctl)} of {len(ctl)}; "
                        f"the crisis pre-check fired on {sum(p['crisis_precheck_fires'] for p in ind)} of {len(ind)}"))
    return out


def baseline_rows(root: Path) -> List[Dict[str, Any]]:
    """AE-15: the standard-library logistic baseline, scored by the Stage W evaluator on the same sets."""
    path = root / "baseline-lr" / "reports" / "evaluation.json"
    source = "SAHAY_TRAINING_ROOT/baseline-lr/reports/evaluation.json"
    if not path.is_file():
        return [row("AE15", "Interpretable logistic baseline", scope="all", status="not_available",
                    evidence_class="none", source=source, note="no baseline report found")]
    out: List[Dict[str, Any]] = []
    for run in json.loads(path.read_text(encoding="utf-8"))["runs"]:
        arm = run["arm"]
        h = run["holdout"]
        out.append(row("AE15", f"Logistic baseline macro F1, fictional holdout ({arm})", scope="synthetic holdout",
                       status="measured", evidence_class="synthetic_development", source=source,
                       value=h["macro"]["f1"], n=h.get("records")))
        for target, w in sorted(run["weak_test"].items()):
            if w["model"].get("auroc") is None:
                continue
            out.append(row("AE15", f"Logistic baseline AUROC vs source label: {target} ({arm})",
                           scope="weak test bucket", status="measured",
                           evidence_class="weak_supervision_from_source_label", source=source,
                           value=w["model"]["auroc"], n=w["n"], note=f"recall {w['model']['recall']}"))
        for corpus, ev in (("dev", "dev"), ("candidates", "candidate")):
            e = run["exposed"][corpus]
            out.append(row("AE15", f"Logistic baseline micro F1 vs deterministic rules ({arm})", scope=corpus,
                           status="measured", evidence_class=EVAL_EVIDENCE[ev], source=source,
                           value=e["model"]["micro_f1"], n=e["samples"],
                           note=f"rules micro F1 {e['rules']['micro_f1']}"))
    return out


def private_rows(training_root: Optional[str], resamples: int, seed: int) -> List[Dict[str, Any]]:
    if not training_root or not Path(training_root).is_dir():
        return [row(mid, name, scope="all", status="not_available", evidence_class="none",
                    source="SAHAY_TRAINING_ROOT", note="private run reports are not available on this machine")
                for mid, name in (("SER", "Speech emotion UAR"), ("TXT", "Text affect UAR"),
                                  ("SHD", "Shadow safety detector (Stage W)"),
                                  ("AE15", "Interpretable logistic baseline"))]
    root = Path(training_root)
    rows = ser_rows(root, resamples, seed) + text_rows(root, resamples, seed) + stage_w_rows(root) + baseline_rows(root)
    if not any(r["metric_id"] == "SER" for r in rows):
        rows.append(row("SER", "Speech emotion UAR", scope="all", status="not_available", evidence_class="none",
                        source="SAHAY_TRAINING_ROOT/ser/runs", note="no run reports found"))
    if not any(r["metric_id"] == "TXT" for r in rows):
        rows.append(row("TXT", "Text affect UAR", scope="all", status="not_available", evidence_class="none",
                        source="SAHAY_TRAINING_ROOT/textaffect/runs-v2", note="no run reports found"))
    return rows


# --------------------------------------------------------------------------- assembly and rendering

def build(eval_report: Optional[Mapping[str, Any]], eval_source: str, training_root: Optional[str],
          resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    if eval_report is not None:
        rows += eval_rows(eval_report, eval_source)
    else:
        for mid, name in (("M1", "Critical-event miss rate"), ("M5", "Red-team cases blocked before synthesis"),
                          ("M7", "Detector precision and recall")):
            rows.append(row(mid, name, scope="all", status="pending", evidence_class="none", source="ml.eval.run_eval",
                            note="no evaluation JSON supplied"))
    rows += static_rows() + private_rows(training_root, resamples, seed)
    locked = (eval_report or {}).get("official_locked_metrics", {}) or {}
    table = {
        "table_version": TABLE_VERSION,
        "eval_source": eval_source if eval_report is not None else None,
        "eval_timestamp": (eval_report or {}).get("timestamp"),
        "eval_commit": ((eval_report or {}).get("git") or {}).get("commit"),
        "versions": (eval_report or {}).get("versions", {}),
        "locked_samples": int(locked.get("locked_samples") or 0),
        "bootstrap": {"resamples": resamples, "seed": seed, "unit": "item (clip or sentence); ignores speaker clustering"},
        "rows": rows,
    }
    check_aggregate_only(table)
    return table


def check_aggregate_only(obj: Any, path: str = "") -> None:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if k in ROW_LEVEL_KEYS:
                raise ValueError(f"row-level key {k!r} at {path or '/'}")
            check_aggregate_only(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            check_aggregate_only(v, f"{path}[{i}]")


def check_wording(text: str, locked_samples: int) -> None:
    folded = text.casefold()
    for phrase in BANNED_PHRASES:
        if phrase in folded:
            raise WordingError(f"banned phrase: {phrase!r}")
    if locked_samples == 0 and re.search(r"\bofficial\b", folded):
        raise WordingError("'official' used while the locked set is empty")


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def render_markdown(table: Mapping[str, Any]) -> str:
    rows = table["rows"]
    out = [
        "# SAHAY-AI evaluation table",
        "",
        f"Table `{table['table_version']}` · evaluation run {table.get('eval_timestamp') or '—'} "
        f"· commit `{(table.get('eval_commit') or '—')[:12]}`",
        "",
        "Every number below comes from the file named in its source column. "
        "`pending` means not measured yet; it is never a zero. "
        "Exposed fixtures were published during development, so results on them show regression behaviour, "
        "not generalisation. Intervals are 95%: Wilson for proportions, item-level bootstrap for UAR "
        f"({table['bootstrap']['resamples']} resamples, seed {table['bootstrap']['seed']}), which ignores speaker "
        "clustering and is therefore optimistic.",
        "",
        f"Locked-set metrics: **pending** ({table['locked_samples']} locked samples).",
        "",
    ]
    if table.get("versions"):
        out += ["Versions: " + ", ".join(f"{k} `{v}`" for k, v in sorted(table["versions"].items())), ""]
    groups = (
        ("Safety routing and red-team (HANDOVER M1, M5)", ("M1", "M1a", "M1b", "M1c", "M1d", "M5")),
        ("Detectors (HANDOVER M7)", ("M7",)),
        ("Abstention and bands", ("A1", "A2")),
        ("Speech emotion (shadow; acted English only)", ("SER",)),
        ("Text affect (shadow)", ("TXT",)),
        ("Shadow safety detector, Stage W (MuRIL, weak supervision; never routes)", ("SHD",)),
        ("Interpretable baseline, AE-15 (standard-library logistic regression; same data and evaluator)", ("AE15",)),
        ("Not yet measured or enforced by tests (HANDOVER M2–M4, M6, M8, M9; D4)",
         ("M2", "M3", "M4", "M6", "M8", "M9", "D4")),
    )
    for title, ids in groups:
        picked = [r for r in rows if r["metric_id"] in ids]
        if not picked:
            continue
        out += [f"## {title}", "", "| ID | Metric | Scope | Value | 95% CI | n | Evidence | Status | Note |",
                "|---|---|---|---|---|---|---|---|---|"]
        for r in picked:
            ci = f"[{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]" if r["ci95"] else "—"
            value = _fmt(r["value"]) if r["status"] == "measured" else f"**{r['status']}**"
            out.append(f"| {r['metric_id']} | {r['metric']} | {r['scope']} | {value} | {ci} | {_fmt(r['n'])} | "
                       f"{r['evidence_class']} | {r['status']} | {r['note']} |")
        out.append("")
    sources = sorted({r["source"] for r in rows})
    out += ["## Sources", ""] + [f"- `{s}`" for s in sources] + [""]
    text = "\n".join(out)
    check_wording(text, table["locked_samples"])
    return text


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SAHAY-AI evaluation table (aggregates only)")
    parser.add_argument("--eval-json", default=None, help="JSON written by python -m ml.eval.run_eval")
    parser.add_argument("--training-root", default=os.environ.get("SAHAY_TRAINING_ROOT"),
                        help="private training root (default: SAHAY_TRAINING_ROOT)")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "runtime" / "eval"))
    parser.add_argument("--tag", default="eval-table")
    parser.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    report = None
    source = "ml.eval.run_eval"
    if args.eval_json:
        path = Path(args.eval_json)
        report = json.loads(path.read_text(encoding="utf-8"))
        source = path.name
    table = build(report, source, args.training_root, args.resamples, args.seed)
    markdown = render_markdown(table)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.tag}.json").write_text(json.dumps(table, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    (out / f"{args.tag}.md").write_text(markdown, encoding="utf-8")
    counts: Dict[str, int] = {}
    for r in table["rows"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"wrote {out / (args.tag + '.md')} ({len(table['rows'])} rows: "
          + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
