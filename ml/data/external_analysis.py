"""Private exploratory analysis of external research data. Stdlib only.

    python -m ml.data.external_analysis run --local-research-override --acknowledge "<sentence>" \\
        [--dataset <id> ...] [--cap 1000] [--seed <seed>]

Output label, exactly: ``external_exploratory_analysis``. The results are
EXPLORATORY FIRING RATES ONLY, produced for private offline research. They are
not product, demo, training, tuning or evaluation evidence, and the sampled
records can never become MVP data.

What it does
------------
For each converted external dataset it draws a deterministic stratified sample,
runs the current deterministic pipeline on it, and reports how often the
pipeline's components fire. That is all. It never tunes a lexicon, threshold,
SVI weight, override, band, abstention rule or guardrail, and it exposes no
option that could.

What it never claims
--------------------
No precision, recall, F1 or accuracy is computed: those need a human-reviewed
SAHAY label, and external source labels are not SAHAY labels. Source labels
are used only to cut *conditional firing rates* — "the crisis pre-check fired
on X% of source rows labelled suicide" — never "crisis recall is X%". The
report refuses the words in ``external_report.FORBIDDEN_WORDS``.

Sampling
--------
For each (source split, stratum) the sample keeps the ``cap`` records with the
smallest SHA-256 of ``seed|record_id``. The stratum is the record's single
source label; for a multi-label dialogue it is the label that occurs on the
most turns (ties broken alphabetically). Duplicates and records that overlap an
exposed SAHAY fixture are left out of the sample. Splits are reported
separately and never pooled before being reported. The whole selection is a
bounded heap per stratum, so the full dataset is streamed, never loaded.

Speakers
--------
A single-text record becomes one victim turn. An EmoInHindi dialogue maps its
``user`` turns to victim turns and its ``bot`` turns to assistant turns, in
source order; assistant turns are not assessed by the pipeline. Any other
speaker value is passed as a victim turn and counted in the report.

Outputs go to ``<SAHAY_DATASETS_ROOT>/reports/external-analysis/`` only.
"""

import argparse
import hashlib
import heapq
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from . import external_corpus as xc
from . import governance as gov
from .external_report import ANALYSIS_LABEL, assert_wording

RUN_VERSION = "1.0.0"
DEFAULT_CAP = 1000
DEFAULT_SEED = "sahay-external-development-2026-09"
SPEAKER_MAP = {"user": "victim", "bot": "assistant", "victim": "victim", "assistant": "assistant",
               "officer": "officer"}
#: Words a result key may never use: there is no SAHAY ground truth here.
FORBIDDEN_METRIC_KEYS = ("precision", "recall", "f1", "accuracy", "sensitivity", "specificity")


def stratum(record: Mapping[str, Any]) -> str:
    """The single source label a record is sampled under."""
    if record.get("turns"):
        counts: Counter = Counter()
        for turn in record["turns"]:
            for cat in turn.get("source_label_category") or []:
                counts[cat] += 1
        if not counts:
            return "source:_unlabelled"
        top = max(counts.values())
        return sorted(c for c, n in counts.items() if n == top)[0]
    cats = record.get("source_label_category") or []
    return cats[0] if len(cats) == 1 else ("|".join(sorted(cats)) or "source:_unlabelled")


def sample(records: Iterable[Mapping[str, Any]], cap: int = DEFAULT_CAP,
           seed: str = DEFAULT_SEED) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Deterministic stratified sample. Streams ``records``; holds at most cap per stratum."""
    heaps: Dict[Tuple[str, str], List[Tuple[str, str, Dict[str, Any]]]] = {}
    seen: Counter = Counter()
    skipped: Counter = Counter()
    for r in records:
        if r.get("duplicate_of"):
            skipped["duplicate"] += 1
            continue
        if r["contamination"]["status"] == "exposed_overlap":
            skipped["exposed_fixture_overlap"] += 1
            continue
        key = (r["source_split"], stratum(r))
        seen[key] += 1
        rank = hashlib.sha256(f"{seed}|{r['record_id']}".encode("utf-8")).hexdigest()
        heap = heaps.setdefault(key, [])
        item = (_neg(rank), r["record_id"], dict(r))
        if len(heap) < cap:
            heapq.heappush(heap, item)
        elif item[0] > heap[0][0]:
            heapq.heapreplace(heap, item)
    chosen: List[Dict[str, Any]] = []
    strata = {}
    for key in sorted(heaps):
        picked = sorted(heaps[key], key=lambda x: x[1])
        chosen += [p[2] for p in picked]
        strata[f"{key[0]}::{key[1]}"] = {"available": seen[key], "sampled": len(picked)}
    method = {"method": "stratified by (source split, source label); within a stratum the cap records with the "
                        "smallest sha256(seed|record_id)", "seed": seed, "cap_per_stratum": cap,
              "strata": strata, "left_out": dict(sorted(skipped.items()))}
    return chosen, method


def _neg(hex_digest: str) -> str:
    """Invert a hex digest so a min-heap keeps the SMALLEST digests."""
    return "".join("0123456789abcdef"[15 - int(c, 16)] for c in hex_digest)


def to_pipeline_sample(record: Mapping[str, Any]) -> Tuple[Dict[str, Any], int]:
    """The evaluator's sample shape. Returns (sample, unmapped_speaker_turns)."""
    unmapped = 0
    if record.get("turns"):
        turns = []
        for i, t in enumerate(record["turns"]):
            speaker = SPEAKER_MAP.get(str(t.get("speaker", "")).lower())
            if speaker is None:
                speaker, unmapped = "victim", unmapped + 1
            turns.append({"id": f"t{i + 1}", "speaker": speaker, "state": "S1", "text": t["text"]})
        if not any(t["speaker"] == "victim" for t in turns):
            turns[0]["speaker"] = "victim"
            unmapped += 1
    else:
        turns = [{"id": "t1", "speaker": "victim", "state": "S1", "text": record["text"]}]
    return {"id": record["record_id"], "turns": turns, "channel": "mobile_chat"}, unmapped


class Tally:
    """Firing counts for one slice. Rates only; no ground truth, so no accuracy."""

    def __init__(self) -> None:
        self.n = 0
        self.c: Counter = Counter()
        self.bands: Counter = Counter()
        self.alerts: Counter = Counter()

    def add(self, p: Mapping[str, Any], evidence_ok: bool, d4_unavailable: bool) -> None:
        self.n += 1
        for cat, v in p["categories"].items():
            if v.get("predicted") is True:
                self.c[f"detector:{cat}"] += 1
        self.c["crisis_precheck"] += bool(p["crisis_precheck"])
        self.c["routed_critical"] += bool(p["routed_critical"])
        self.c["abstained"] += bool(p["abstained"])
        self.c["needs_human_assessment"] += p["band"] is None
        self.c["d4_unavailable"] += d4_unavailable
        self.c["evidence_links_valid"] += evidence_ok
        if p["band"] is not None:
            self.bands[p["band"]] += 1
        for key in p["cited_evidence"]:
            if key.startswith("alert:"):
                self.alerts[key.split(":", 1)[1]] += 1

    def rates(self) -> Dict[str, Any]:
        def rate(k: str) -> Optional[float]:
            return round(self.c[k] / self.n, 4) if self.n else None
        detectors = sorted(k for k in self.c if k.startswith("detector:"))
        return {
            "n": self.n,
            "firing_rate": {k.split(":", 1)[1]: rate(k) for k in detectors},
            "crisis_precheck_firing_rate": rate("crisis_precheck"),
            "routed_critical_rate": rate("routed_critical"),
            "abstention_rate": rate("abstained"),
            "needs_human_assessment_rate": rate("needs_human_assessment"),
            "scored_band_distribution": dict(sorted(self.bands.items())),
            "alert_distribution": dict(sorted(self.alerts.items())),
            "d4_unavailable_rate": rate("d4_unavailable"),
            "evidence_link_validity_rate": rate("evidence_links_valid"),
        }


def run(root: Path, override: Mapping[str, Any], datasets: Optional[List[str]] = None,
        cap: int = DEFAULT_CAP, seed: str = DEFAULT_SEED,
        registry: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Sample, run the pipeline, and write the private report. Needs the override."""
    reg = registry if registry is not None else gov.load_registry()
    ids = datasets or [r["id"] for r in reg["datasets"] if r["id"] in xc.SPECS]
    for dataset_id in ids:
        xc.authorise(reg, dataset_id, "local_research_exploratory_analysis", override)
    from ..eval.predict import predict  # lazy: only after every dataset is authorised

    started = xc.now()
    results: Dict[str, Any] = {}
    for dataset_id in ids:
        stream = xc.iter_normalized(root, dataset_id, reg)
        if stream is None:
            results[dataset_id] = {"status": "not_converted"}
            continue
        chosen, method = sample(stream, cap, seed)
        overall = Tally()
        slices: Dict[str, Dict[str, Tally]] = {"source_split": {}, "source_label": {}, "language": {},
                                                "script": {}}
        by_split_label: Dict[str, Tally] = {}
        unmapped_turns = 0
        t0 = time.perf_counter()
        for record in chosen:
            pipeline_sample, unmapped = to_pipeline_sample(record)
            unmapped_turns += unmapped
            p = predict(pipeline_sample)
            victim = set(p["victim_turn_ids"])
            evidence_ok = all(i in victim for ids_ in p["cited_evidence"].values() for i in ids_) and all(
                set(c["evidence"]) <= victim for c in p["categories"].values() if c.get("predicted"))
            # the same test ml/eval/evaluate.py::_d4 applies to text channels
            d4_unavailable = (p["normalization"] or {}).get("structurally_unavailable") == ["D4"] and \
                (p["d4"] or {}).get("score") is None and (p["d4"] or {}).get("confidence") is None
            overall.add(p, evidence_ok, d4_unavailable)
            label = stratum(record)
            for name, key in (("source_split", record["source_split"]), ("source_label", label),
                              ("language", record["language"]), ("script", record["script"])):
                slices[name].setdefault(key, Tally()).add(p, evidence_ok, d4_unavailable)
            by_split_label.setdefault(f"{record['source_split']}::{label}", Tally()).add(p, evidence_ok,
                                                                                         d4_unavailable)
        elapsed = time.perf_counter() - t0
        results[dataset_id] = {
            "status": "run",
            "sampling": method,
            "overall": overall.rates(),
            "by_split_and_source_label": {k: v.rates() for k, v in sorted(by_split_label.items())},
            "slices": {name: {k: v.rates() for k, v in sorted(group.items())} for name, group in slices.items()},
            "unmapped_speaker_turns": unmapped_turns,
            "guardrails": {"applicable": False,
                           "reason": "the assessment path produces no assistant text, so no guardrail was invoked"},
            "runtime_seconds": round(elapsed, 3),
            "records_per_second": round(len(chosen) / elapsed, 1) if elapsed else None,
        }
    report = {
        "label": ANALYSIS_LABEL,
        "result_kind": "exploratory firing rates only",
        "run_version": RUN_VERSION,
        "run_at": started,
        "governance_basis": xc.OVERRIDE_BASIS,
        "licence_approved": False,
        "privacy_approved": False,
        "product_use_permitted": False,
        "operator": override.get("operator", "unspecified"),
        "tuning_performed": False,
        "ground_truth": "none: source labels are not SAHAY labels, so only conditional firing rates are reported",
        "datasets": results,
        "statement": "external_exploratory_analysis: exploratory firing rates of the current deterministic "
                     "pipeline on private external research samples. Not a measure of correctness; no SAHAY "
                     "label exists for these records. The records cannot enter the product or demo and are not "
                     "for training, tuning, the locked or blind corpus, or any published claim.",
    }
    check_report(report)
    out = xc.reports_dir(root, "external-analysis")
    out.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(report, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    text = render(report)
    for name, body in (("external_exploratory_analysis.json", blob),
                       ("external_exploratory_analysis.md", text)):
        tmp = out / (name + ".partial")
        tmp.write_text(body, encoding="utf-8", newline="\n")
        os.replace(tmp, out / name)
    xc.record_override_use(root, {"event": "local_research_override_exploratory_analysis", "at": started,
                                  "datasets": ids, "cap": cap, "seed": seed, "operator": report["operator"],
                                  "licence_approved": False, "privacy_approved": False,
                                  "report_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()})
    return report


def check_report(report: Mapping[str, Any]) -> None:
    """Refuse forbidden wording and any accuracy-style metric key."""
    blob = json.dumps(report, ensure_ascii=False)
    assert_wording(blob)

    def walk(obj: Any) -> None:
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                low = str(k).lower()
                if any(word in low for word in FORBIDDEN_METRIC_KEYS):
                    raise ValueError(f"an accuracy-style metric key is not allowed here: {k}")
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
    walk(report)


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def render(report: Mapping[str, Any]) -> str:
    out = [f"# {report['label']} — exploratory firing rates only", "",
           f"Run {report['run_at']} · governance basis `{report['governance_basis']}` · licence approved: "
           f"{report['licence_approved']} · privacy approved: {report['privacy_approved']} · product use "
           f"permitted: {report['product_use_permitted']} · tuning performed: {report['tuning_performed']}", "",
           report["statement"], ""]
    for dataset_id, res in report["datasets"].items():
        out += [f"## `{dataset_id}`", ""]
        if res["status"] != "run":
            out += [f"Status: {res['status']}.", ""]
            continue
        o = res["overall"]
        out += [f"Sample: {o['n']} record(s); {res['sampling']['method']}; seed `{res['sampling']['seed']}`; "
                f"left out {res['sampling']['left_out']}; {res['records_per_second']} records/s.", "",
                f"- crisis pre-check fired on {_pct(o['crisis_precheck_firing_rate'])} of sampled records",
                f"- routed Critical on {_pct(o['routed_critical_rate'])}",
                f"- abstained / Needs Human Assessment on {_pct(o['needs_human_assessment_rate'])}",
                f"- scored bands where a score exists: {o['scored_band_distribution']}",
                f"- alerts: {o['alert_distribution']}",
                f"- D4 structurally unavailable on {_pct(o['d4_unavailable_rate'])}",
                f"- evidence links valid on {_pct(o['evidence_link_validity_rate'])}", "",
                "| Split :: source label | n | crisis pre-check fired | routed Critical | Needs Human Assessment |",
                "|---|---:|---:|---:|---:|"]
        for key, r in res["by_split_and_source_label"].items():
            out.append(f"| `{key}` | {r['n']} | {_pct(r['crisis_precheck_firing_rate'])} | "
                       f"{_pct(r['routed_critical_rate'])} | {_pct(r['needs_human_assessment_rate'])} |")
        out += ["", "Detector firing rate on sampled records:", ""]
        for det, r in o["firing_rate"].items():
            out.append(f"- `{det}` fired on {_pct(r)}")
        out.append("")
    text = "\n".join(out) + "\n"
    assert_wording(text)
    return text


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="external_exploratory_analysis: exploratory firing rates only")
    parser.add_argument("--root", default=None, help=f"dataset root (default: ${gov.ROOT_ENV})")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="sample private external research data and run the current pipeline")
    r.add_argument("--dataset", action="append", default=None)
    r.add_argument("--cap", type=int, default=DEFAULT_CAP)
    r.add_argument("--seed", default=DEFAULT_SEED)
    xc.add_override_arguments(r)
    args = parser.parse_args(argv)
    try:
        override = xc.override_from_args(args)
        if override is None:
            raise xc.AdapterRefused(f"external data is licence_pending; this private research run needs "
                                    f"{xc.OVERRIDE_FLAG} and the acknowledgement sentence")
        root = gov.dataset_root(args.root)
        report = run(root, override, args.dataset, args.cap, args.seed)
    except (gov.DatasetRootError, gov.GovernanceError) as exc:
        print(f"configuration: {exc}")
        return 4
    except xc.AdapterRefused as exc:
        print(f"run refused: {exc}")
        return 3
    for dataset_id, res in report["datasets"].items():
        if res["status"] == "run":
            o = res["overall"]
            print(f"{dataset_id}: n={o['n']}, crisis pre-check fired {_pct(o['crisis_precheck_firing_rate'])}, "
                  f"routed Critical {_pct(o['routed_critical_rate'])}, Needs Human Assessment "
                  f"{_pct(o['needs_human_assessment_rate'])}, D4 unavailable {_pct(o['d4_unavailable_rate'])}")
        else:
            print(f"{dataset_id}: {res['status']}")
    print(f"{ANALYSIS_LABEL} (exploratory firing rates only) written to the private reports directory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
