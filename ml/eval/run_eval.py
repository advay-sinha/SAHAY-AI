"""SAHAY-AI deterministic ML evaluation. Standard library only.

    python -m ml.eval.run_eval                      # all splits -> runtime/eval/
    python -m ml.eval.run_eval --corpus dev         # one split
    python -m ml.eval.run_eval --out ml/eval/results --tag baseline

Runs with networking disabled, LLM credentials hidden, and no model, audio or
deep-learning package; it fails if any of those is touched. Writes
eval-<tag>.json (machine-readable) and eval-<tag>.md (human-readable).

Split discipline:
  dev         may be used for tuning; its numbers are development numbers
  candidate   never used for tuning; unofficial until reviewed
  locked      the only split whose numbers are official; empty until real
              reviews are recorded, so official critical-safety metrics are
              PENDING (reported as such, never back-filled from other splits)
"""

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping

from ..assessment import PIPELINE_VERSION
from ..guardrails.crisis_precheck import LEXICON_VERSION
from ..guardrails.validator import VALIDATOR_VERSION
from ..svi.dimensions import SCORING_VERSION
from . import checks, redteam, svi_sensitivity
from .evaluate import evaluate, headline
from .metrics import fmt
from .predict import NOT_IMPLEMENTED
from .schema import (
    CRITICAL_CATEGORIES,
    SCHEMA_VERSION,
    disjoint,
    identifying_data,
    is_critical,
    lock_eligible,
    validate_corpus,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
SPLIT_FILES = {"dev": "dev.json", "candidate": "candidates.json", "locked": "locked.json"}


def load(name: str) -> Dict[str, Any]:
    return json.loads((CORPUS_DIR / name).read_text(encoding="utf-8"))


def git_state() -> Dict[str, Any]:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "ml"], cwd=ROOT, capture_output=True,
                               text=True, timeout=10).stdout.strip()
        return {"commit": head or "unknown", "ml_tree_dirty": bool(dirty)}
    except (OSError, subprocess.SubprocessError):
        return {"commit": "unknown", "ml_tree_dirty": None}


def _exclusions(corpus: Mapping[str, Any]) -> Dict[str, Any]:
    samples = corpus["samples"]
    out: Dict[str, Any] = {"categories": dict(NOT_IMPLEMENTED)}
    if corpus["split"] == "locked":
        bad = [s["id"] for s in samples if not lock_eligible(s)]
        out["samples_excluded"] = {sid: "not lock-eligible" for sid in bad}
    else:
        out["samples_excluded"] = {}
        out["official_status"] = ("development numbers (tuning allowed)" if corpus["split"] == "dev"
                                  else "unofficial: samples pending human review")
        pending_critical = [s["id"] for s in samples if is_critical(s) and not lock_eligible(s)]
        out["critical_samples_pending_review"] = len(pending_critical)
    return out


def build_report(splits: List[str], timestamp: str) -> Dict[str, Any]:
    corpora = {split: load(SPLIT_FILES[split]) for split in SPLIT_FILES}
    schema_errors = {split: validate_corpus(c) for split, c in corpora.items()}
    rt_corpus = load("redteam.json")

    with checks.offline() as offline_report:
        per_split = {}
        for split in splits:
            c = corpora[split]
            included = [s for s in c["samples"] if split != "locked" or lock_eligible(s)]
            per_split[split] = {
                "corpus_version": c["corpus_version"],
                "sample_count": len(c["samples"]),
                "included": len(included),
                "excluded": len(c["samples"]) - len(included),
                "exclusions": _exclusions(c),
                "result": evaluate(included) if included else None,
            }
        rt = redteam.run(rt_corpus)
        coverage = redteam.prohibition_coverage()
        svi = svi_sensitivity.run()
        dev_samples = corpora["dev"]["samples"]
        det = checks.determinism(lambda: evaluate(dev_samples))
        replay = checks.scenario_replay([s for c in corpora.values() for s in c["samples"]])
        llm = checks.llm_off()

    locked = corpora["locked"]
    official = {
        "locked_samples": len(locked["samples"]),
        "lock_eligible": sum(1 for s in locked["samples"] if lock_eligible(s)),
        "critical_safety_metrics": (
            "PENDING: the locked set has no lock-eligible samples; crisis and immediate-danger samples need "
            "two real reviewer approvals" if not any(lock_eligible(s) for s in locked["samples"])
            else "available"),
        "critical_categories": list(CRITICAL_CATEGORIES),
    }
    return {
        "report": "sahay-ml-evaluation",
        "timestamp": timestamp,
        "git": git_state(),
        "python": platform.python_version(),
        "versions": {
            "label_schema": SCHEMA_VERSION,
            "corpus": corpora["dev"]["corpus_version"],
            "redteam_corpus": rt_corpus["corpus_version"],
            "scoring": SCORING_VERSION,
            "pipeline": PIPELINE_VERSION,
            "crisis_lexicon": LEXICON_VERSION,
            "validator": VALIDATOR_VERSION,
        },
        "schema_validation": schema_errors,
        "split_disjointness": disjoint(list(corpora.values())),
        "identifying_data": identifying_data([s for c in corpora.values() for s in c["samples"]]),
        "official_locked_metrics": official,
        "splits": per_split,
        "redteam": rt,
        "prohibition_coverage": coverage,
        "svi_sensitivity": svi,
        "checks": {"determinism": det, "scenario_replay": replay, "llm_off": llm,
                   "offline": offline_report, "static_imports": checks.static_imports(ROOT / "ml")},
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _detector_rows(table: Mapping[str, Any]) -> List[str]:
    rows = ["| Detector | TP | FP | FN | TN | Precision (den.) | Recall (den.) | F1 |", "|---|---|---|---|---|---|---|---|"]
    for cat, m in table.items():
        if "excluded" in m:
            rows.append(f"| {cat} | — | — | — | — | excluded: {m['excluded']} ({m['labelled_positives']} labelled) | | |")
            continue
        rows.append(f"| {cat} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | "
                    f"{fmt(m['precision'])} ({m['precision_denominator']}) | "
                    f"{fmt(m['recall'])} ({m['recall_denominator']}) | {fmt(m['f1'])} |")
    return rows


def render_markdown(r: Mapping[str, Any]) -> str:
    v = r["versions"]
    out = [
        "# SAHAY-AI ML evaluation report", "",
        f"- Timestamp: {r['timestamp']}",
        f"- Git commit: `{r['git']['commit']}` (ml/ tree dirty: {r['git']['ml_tree_dirty']})",
        f"- Label schema {v['label_schema']} · corpus {v['corpus']} · scoring {v['scoring']} · "
        f"pipeline {v['pipeline']} · crisis lexicon {v['crisis_lexicon']} · validator {v['validator']}",
        "- Deterministic text pipeline; no LLM, no network, no model, no audio.", "",
        "## Official locked-set metrics", "",
        f"**{r['official_locked_metrics']['critical_safety_metrics']}.** "
        f"Locked samples: {r['official_locked_metrics']['locked_samples']}.", "",
        "Numbers below are development (dev) and unofficial (candidate) numbers. They are not validation.", "",
    ]
    for split, s in r["splits"].items():
        out += [f"## Split: {split}", "",
                f"Samples {s['sample_count']}, included {s['included']}, excluded {s['excluded']}. "
                f"Status: {s['exclusions'].get('official_status', 'official')}.", ""]
        if s["exclusions"].get("categories"):
            for cat, why in s["exclusions"]["categories"].items():
                out.append(f"- Excluded category `{cat}`: {why}.")
            out.append("")
        res = s["result"]
        if res is None:
            out += ["No eligible samples: nothing to report.", ""]
            continue
        h = headline(res)
        rt = res["routing"]
        out += [f"**Critical misses: {h['critical_miss_count']} of {h['critical_events']} critical events "
                f"(miss rate {fmt(h['critical_miss_rate'])}). False escalations: {h['false_escalation_count']}.**", ""]
        out += _detector_rows(res["detectors"]) + [""]
        out += ["| Language | n | Critical events | Missed | False escalations |", "|---|---|---|---|---|"]
        for lang, pl in res["per_language"].items():
            m = pl["routing"]["critical_event_miss_rate"]
            out.append(f"| {lang} | {pl['n']} | {m['critical_events']} | {m['missed']} | "
                       f"{len(pl['routing']['false_escalations'])} |")
        out.append("")
        out += ["| Slice | n | Critical events | Missed | False escalations | Crisis pre-check P / R |",
                "|---|---|---|---|---|---|"]
        for name, sl in res["slices"].items():
            m = sl["routing"]["critical_event_miss_rate"]
            cp = sl["routing"]["crisis_precheck"]
            out.append(f"| {name} | {sl['n']} | {m['critical_events']} | {m['missed']} | "
                       f"{len(sl['routing']['false_escalations'])} | {fmt(cp['precision'])} / {fmt(cp['recall'])} |")
        out.append("")
        if rt["critical_misses"]:
            out += ["Critical misses:", ""] + [f"- `{m['id']}` ({m['language']}): expected {m['expected']}; "
                                               f"actual {m['actual']}" for m in rt["critical_misses"]] + [""]
        if rt["false_escalations"]:
            out += ["False escalations:", ""] + [f"- `{m['id']}` ({m['language']}): expected {m['expected']}; "
                                                 f"actual {m['actual']}" for m in rt["false_escalations"]] + [""]
        ev, ab, bd = res["evidence"], res["abstention"], res["bands"]
        out += [f"Evidence: {ev['cited_ids_valid']}/{ev['cited_ids']} cited ids are real victim turns; "
                f"{ev['positives_with_valid_evidence']}/{ev['positive_predictions']} positive predictions cite "
                f"valid evidence; labelled-evidence overlap on true positives {fmt(ev['evidence_overlap_rate'])} "
                f"(exact {fmt(ev['evidence_exact_rate'])}, n={ev['true_positives_with_labels']}).", "",
                f"Abstention: {ab['abstained_when_expected']}/{ab['expected_abstain']} expected abstentions "
                f"(coverage {fmt(ab['abstention_coverage'])}); {ab['scored_when_expected']}/{ab['expected_score']} "
                f"expected scores; {ab['unspecified']} samples unspecified; {ab['abstained_total']} abstained in total.", "",
                f"Band distribution: {bd['distribution']}. Expected-band agreement {bd['band_agreement']}/"
                f"{bd['band_specified']} ({fmt(bd['band_agreement_rate'])}).", "",
                f"D4 checks: {res['d4']['checked']} samples, problems: {res['d4']['problems'] or 'none'}.", ""]
    rt = r["redteam"]
    out += ["## Guardrail red-team", "",
            f"{rt['passed']}/{rt['cases']} cases pass (pass rate {fmt(rt['pass_rate'])}). "
            f"Known failures by severity: {rt['failures_by_severity']}.", "",
            "| Fixture | Severity | Category | Expected | Actual |", "|---|---|---|---|---|"]
    for f in rt["failures"]:
        out.append(f"| `{f['id']}` | {f['severity']} | {f['category']} | {f['expected']} | {f['actual']} |")
    pc = r["prohibition_coverage"]
    out += ["", f"Prohibition coverage: {pc['with_both_languages']}/{pc['prohibitions']} prohibitions have Hindi and "
            f"English markers; {pc['with_hinglish_markers']} have romanised Hinglish markers.", ""]
    out += ["## SVI sensitivity (frozen values, analysed not changed)", ""]
    out += [f"- {f}" for f in r["svi_sensitivity"]["findings"]] + [""]
    c = r["checks"]
    out += ["## Reproducibility", "",
            f"- Determinism: {c['determinism']['runs']} runs identical = {c['determinism']['identical']}.",
            f"- Scenario replay: {c['scenario_replay']['multi_turn_samples']} multi-turn samples, "
            f"inconsistent: {c['scenario_replay']['inconsistent'] or 'none'}.",
            f"- LLM-off: completed = {c['llm_off']['completed']} "
            f"({c['llm_off']['rephrasable_fallbacks_checked']} fallbacks validated); problems: "
            f"{c['llm_off']['problems'] or 'none'}.",
            f"- Offline: network attempts {len(c['offline']['network_attempts'])}, forbidden modules "
            f"{c['offline']['forbidden_modules_loaded'] or 'none'}; static import offenders "
            f"{c['static_imports']['offenders'] or 'none'}.",
            f"- Schema errors: {sum(len(e) for e in r['schema_validation'].values())}; split overlap: "
            f"{r['split_disjointness'] or 'none'}; identifying-data hits: {r['identifying_data'] or 'none'}.", ""]
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SAHAY-AI deterministic ML evaluation")
    parser.add_argument("--corpus", choices=["dev", "candidate", "locked", "all"], default="all")
    parser.add_argument("--out", default=str(ROOT / "runtime" / "eval"))
    parser.add_argument("--tag", default=None, help="output file suffix (default: the corpus name)")
    parser.add_argument("--timestamp", default=None, help="override the execution timestamp (ISO 8601)")
    args = parser.parse_args(argv)

    splits = list(SPLIT_FILES) if args.corpus == "all" else [args.corpus]
    stamp = args.timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report = build_report(splits, stamp)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = args.tag or args.corpus
    (out / f"eval-{tag}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                          encoding="utf-8", newline="\n")
    (out / f"eval-{tag}.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")

    c = report["checks"]
    blocking = []
    if any(report["schema_validation"].values()):
        blocking.append("schema errors")
    if report["split_disjointness"]:
        blocking.append("split overlap")
    if report["identifying_data"]:
        blocking.append("identifying data")
    if not c["offline"]["ok"] or not c["static_imports"]["ok"]:
        blocking.append("offline/import violation")
    if not c["determinism"]["identical"] or not c["scenario_replay"]["consistent"]:
        blocking.append("non-determinism")
    for split, s in report["splits"].items():
        res = s["result"]
        h = headline(res) if res else None
        print(f"{split}: {s['included']}/{s['sample_count']} samples"
              + (f", critical misses {h['critical_miss_count']}/{h['critical_events']}, "
                 f"false escalations {h['false_escalation_count']}" if h else ", nothing eligible"))
    print(f"red-team: {report['redteam']['passed']}/{report['redteam']['cases']} pass; "
          f"official locked metrics: {report['official_locked_metrics']['critical_safety_metrics'][:7]}")
    print(f"wrote {out / f'eval-{tag}.json'} and .md")
    if blocking:
        print("BLOCKING: " + ", ".join(blocking))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
