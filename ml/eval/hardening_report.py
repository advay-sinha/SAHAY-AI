"""Safety-hardening report (2026-09-11). Standard library only, offline.

    python -m ml.eval.hardening_report                  # -> ml/eval/results/safety-hardening-2026-09-11.{json,md}
    python -m ml.eval.hardening_report --out runtime/eval

The baseline report is READ, never rewritten. Results are kept in separate
sections, and none of them is presented as generalisation:

  baseline            numbers exactly as published in eval-baseline-2026-09-11.json
  exposed_regression  before/after for every fixture whose failure was published
                      (ml/eval/contamination.py). Improvement here is REGRESSION
                      performance: these sentences were read while the fixes
                      were designed.
  candidate           the candidate split, all of it exposed; unreviewed
  locked_official     unavailable: the locked set is empty
  remaining_failures  everything still failing, by fixture id
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..guardrails.crisis_precheck import LEXICON_VERSION
from ..guardrails.lexicons.output_rules import RULES, RULES_VERSION
from ..guardrails.validator import VALIDATOR_VERSION
from ..svi.dimensions import SCORING_VERSION
from . import checks, contamination, redteam, svi_sensitivity
from .evaluate import evaluate, headline
from .metrics import fmt
from .run_eval import git_state

ROOT = Path(__file__).resolve().parents[2]
EVAL = Path(__file__).resolve().parent
BASELINE = EVAL / "results" / "eval-baseline-2026-09-11.json"
TAG = "safety-hardening-2026-09-11"


def _load(name: str) -> Dict[str, Any]:
    return json.loads((EVAL / "corpus" / name).read_text(encoding="utf-8"))


def _fixture_row(sid: str, sample: Dict[str, Any], before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    def failures(pred):
        out = []
        for cat, v in pred["categories"].items():
            if v["predicted"] is not None and v["predicted"] != sample["labels"][cat]:
                out.append(("FN:" if sample["labels"][cat] else "FP:") + cat)
        if pred["routed_critical"] != sample["expected"]["routed_critical"]:
            out.append("ROUTING")
        return sorted(out)

    b, a = failures(before), failures(after)
    evidence = {cat: {"before": before["categories"][cat]["evidence"], "after": after["categories"][cat]["evidence"]}
                for cat in after["categories"]
                if before["categories"][cat]["evidence"] != after["categories"][cat]["evidence"]}
    status = "fixed" if b and not a else ("unchanged" if b == a else "changed")
    if status == "unchanged" and evidence:
        status = "evidence changed"
    return {"id": sid, "before_failures": b, "after_failures": a, "evidence_changes": evidence,
            "before": {"routed": before["routed_critical"], "band": before["band"], "precheck": before["crisis_precheck"]},
            "after": {"routed": after["routed_critical"], "band": after["band"], "precheck": after["crisis_precheck"]},
            "status": status}


def build(timestamp: str) -> Dict[str, Any]:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    dev, cand, locked = _load("dev.json"), _load("candidates.json"), _load("locked.json")
    rt, rth, rtu = _load("redteam.json"), _load("redteam_hardening.json"), _load("redteam_urgency.json")

    with checks.offline() as net, checks.file_access_log() as opened:
        dev_now = evaluate(dev["samples"])
        cand_now = evaluate(cand["samples"])
        rt_now = redteam.run(rt)
        rth_now = redteam.run(rth)
        rtu_now = redteam.run(rtu)
        coverage = redteam.prohibition_coverage()
        svi_now = svi_sensitivity.run()
        det = checks.determinism(lambda: (evaluate(dev["samples"]), redteam.run(rth), redteam.run(rtu)))
        llm = checks.llm_off()
        replay = checks.scenario_replay(dev["samples"] + cand["samples"])

    b_dev = baseline["splits"]["dev"]["result"]
    b_cand = baseline["splits"]["candidate"]["result"]
    samples = {s["id"]: s for s in dev["samples"] + cand["samples"]}
    preds_before = {**b_dev["predictions"], **b_cand["predictions"]}
    preds_after = {**dev_now["predictions"], **cand_now["predictions"]}

    exposed_ids = sorted(set(contamination.CANDIDATE_KNOWN_FAILURES) | set(contamination.DEV_KNOWN_FAILURES)
                         | {i for i in contamination.REGRESSION_TARGETS_HARDENING if i in samples})
    fixture_rows = [_fixture_row(i, samples[i], preds_before[i], preds_after[i]) for i in exposed_ids]
    # Evidence-precision target: the coercion over-citation is an evidence change, not a label failure.
    ev_before = [x for x in b_dev["evidence"].get("invalid", [])]

    rt_before = {r["id"]: r for r in baseline["redteam"]["results"]}
    rt_rows = [{"id": r["id"], "severity": r["severity"], "category": r["category"],
                "before": rt_before[r["id"]]["actual"], "after": r["actual"],
                "status": "fixed" if not rt_before[r["id"]]["passed"] and r["passed"]
                else ("still failing" if not r["passed"] else "passing before and after")}
               for r in rt_now["results"]]

    remaining: List[Dict[str, Any]] = []
    for split, res in (("dev", dev_now), ("candidate", cand_now)):
        for m in res["routing"]["critical_misses"]:
            remaining.append({"id": m["id"], "kind": "critical_miss", "split": split, "actual": m["actual"]})
        for m in res["routing"]["false_escalations"]:
            remaining.append({"id": m["id"], "kind": "false_escalation", "split": split, "actual": m["actual"]})
    for row in fixture_rows:
        for f in row["after_failures"]:
            if f.startswith(("FN:", "FP:")):
                remaining.append({"id": row["id"], "kind": "detector_" + f.split(":")[0].lower(), "split":
                                  "dev" if row["id"].startswith("DEV") else "candidate", "actual": f})
    for corpus_name, res in (("redteam", rt_now), ("redteam_hardening", rth_now), ("redteam_urgency", rtu_now)):
        for f in res["failures"]:
            remaining.append({"id": f["id"], "kind": "guardrail_failure", "split": corpus_name,
                              "actual": f["actual"], "severity": f["severity"]})

    def crisis(res):
        m = res["detectors"]["crisis_self_harm"]
        return {k: m[k] for k in ("tp", "fp", "fn", "tn", "precision", "recall")}

    return {
        "report": "sahay-ml-safety-hardening",
        "timestamp": timestamp,
        "git": git_state(),
        "versions": {"scoring": SCORING_VERSION, "crisis_lexicon": LEXICON_VERSION,
                     "validator": VALIDATOR_VERSION, "output_rules": RULES_VERSION, "output_rule_count": len(RULES),
                     "corpus": dev["corpus_version"], "redteam_hardening_corpus": rth["corpus_version"],
                     "redteam_urgency_corpus": rtu["corpus_version"],
                     "baseline_versions": baseline["versions"]},
        "baseline": {
            "dev": headline(b_dev), "candidate": headline(b_cand),
            "dev_crisis": {k: b_dev["detectors"]["crisis_self_harm"][k] for k in ("tp", "fp", "fn", "tn", "precision", "recall")},
            "redteam": {"passed": baseline["redteam"]["passed"], "cases": baseline["redteam"]["cases"]},
        },
        "exposed_regression": {
            "label": "REGRESSION performance on fixtures whose failure was published and read while designing fixes. "
                     "Not evidence of generalisation.",
            "fixtures": fixture_rows,
            "fixed": [r["id"] for r in fixture_rows if r["status"] == "fixed"],
            "still_failing": [r["id"] for r in fixture_rows if r["after_failures"]],
            "redteam": rt_rows,
            "redteam_now": {"passed": rt_now["passed"], "cases": rt_now["cases"]},
            "baseline_evidence_invalid": ev_before,
        },
        "development_evidence": {
            "label": "Near-miss and paraphrase cases written by the rule author alongside the rules: development "
                     "evidence of overbreadth, not holdout evidence.",
            "redteam_hardening": {"passed": rth_now["passed"], "cases": rth_now["cases"],
                                  "failures": rth_now["failures"], "by_category": rth_now["by_category"]},
            "redteam_urgency": {"label": "Urgency-level leakage and approved-reference boundary cases added after "
                                         "the hardening review; reported separately from the 39 regressions.",
                                "passed": rtu_now["passed"], "cases": rtu_now["cases"],
                                "failures": rtu_now["failures"], "by_category": rtu_now["by_category"]},
            "known_limitation": "Bare numbers without score/priority wording (\"Your number is 82\") are "
                                "deliberately not blocked: they may be legitimate references. Structural "
                                "mitigation proposed as PROPOSALS.md P-BND-1.",
        },
        "current": {
            "dev": {"headline": headline(dev_now), "crisis": crisis(dev_now), "evidence": {
                k: v for k, v in dev_now["evidence"].items() if k != "invalid"}, "d4_problems": dev_now["d4"]["problems"],
                "abstention": {k: v for k, v in dev_now["abstention"].items()}},
            "candidate": {"label": "unreviewed and fully exposed (every outcome published 2026-09-11): regression, not holdout",
                          "headline": headline(cand_now), "crisis": crisis(cand_now),
                          "evidence": {k: v for k, v in cand_now["evidence"].items() if k != "invalid"},
                          "d4_problems": cand_now["d4"]["problems"]},
        },
        "locked_official": {"status": "UNAVAILABLE: the locked set is empty; no fixture-level human review has "
                                      "occurred (the two code-level crisis reviews are not fixture reviews)",
                            "locked_samples": len(locked["samples"])},
        "remaining_failures": remaining,
        "invariants": {
            "svi_sensitivity_findings": svi_now["findings"],
            "svi_sensitivity_unchanged": {k: svi_now[k] == baseline["svi_sensitivity"][k]
                                          for k in svi_now if k in baseline["svi_sensitivity"]},
            "prohibition_coverage": {"prohibitions": coverage["prohibitions"],
                                     "with_both_languages": coverage["with_both_languages"]},
        },
        "checks": {"offline": net, "external_corpus_access": checks.external_corpus_access(opened),
                   "files_opened": len(opened), "determinism": det, "llm_off": llm, "scenario_replay": replay,
                   "static_imports": checks.static_imports(ROOT / "ml")},
    }


def render(r: Dict[str, Any]) -> str:
    b, ex, cur = r["baseline"], r["exposed_regression"], r["current"]
    out = [
        "# SAHAY-AI safety-hardening report — 2026-09-11", "",
        f"- Timestamp: {r['timestamp']} · Git: `{r['git']['commit']}` (ml/ tree dirty: {r['git']['ml_tree_dirty']})",
        f"- Scoring {r['versions']['scoring']} (unchanged) · crisis lexicon {r['versions']['crisis_lexicon']} · "
        f"validator {r['versions']['validator']} · output rules {r['versions']['output_rules']} "
        f"({r['versions']['output_rule_count']} rules)",
        "- The baseline report `eval-baseline-2026-09-11.{json,md}` is unchanged; its numbers are quoted below.", "",
        "## Official locked metrics", "", f"**{r['locked_official']['status']}.**", "",
        "## 1. Baseline (as published)", "",
        "| | Dev | Candidate |", "|---|---|---|",
        f"| Critical misses / events | {b['dev']['critical_miss_count']} / {b['dev']['critical_events']} | "
        f"{b['candidate']['critical_miss_count']} / {b['candidate']['critical_events']} |",
        f"| False escalations | {b['dev']['false_escalation_count']} | {b['candidate']['false_escalation_count']} |",
        f"| Red-team | {b['redteam']['passed']}/{b['redteam']['cases']} pass | |", "",
        "## 2. Exposed-regression results — REGRESSION performance, not generalisation", "",
        ex["label"], "",
        "| Fixture | Before | After | Status |", "|---|---|---|---|",
    ]
    for f in ex["fixtures"]:
        ev = "; ".join(f"{c} evidence {v['before']} -> {v['after']}" for c, v in f["evidence_changes"].items())
        out.append(f"| `{f['id']}` | {', '.join(f['before_failures']) or 'none'} | "
                   f"{', '.join(f['after_failures']) or 'none'}{(' (' + ev + ')') if ev else ''} | {f['status']} |")
    out += ["", f"Red-team (baseline corpus, all exposed): {ex['redteam_now']['passed']}/{ex['redteam_now']['cases']} "
            f"pass now, {b['redteam']['passed']}/{b['redteam']['cases']} before.", "",
            "| Fixture | Severity | Before | After | Status |", "|---|---|---|---|---|"]
    for row in ex["redteam"]:
        if row["status"] != "passing before and after":
            out.append(f"| `{row['id']}` | {row['severity']} | {row['before']} | {row['after']} | {row['status']} |")
    d = r["development_evidence"]["redteam_hardening"]
    out += ["", "## 3. Development evidence (rule author's near-misses and paraphrases)", "",
            r["development_evidence"]["label"], "",
            f"{d['passed']}/{d['cases']} pass. Failures: {[f['id'] for f in d['failures']] or 'none'}.", ""]
    u = r["development_evidence"]["redteam_urgency"]
    out += ["### 3b. Urgency-level leakage and approved references (added after review; reported separately)", "",
            u["label"], "",
            f"{u['passed']}/{u['cases']} pass. Failures: {[f['id'] for f in u['failures']] or 'none'}. "
            f"Categories: " + ", ".join(f"{k} {v['passed']}/{v['cases']}" for k, v in u["by_category"].items()) + ".",
            "", f"Known limitation: {r['development_evidence']['known_limitation']}", ""]
    out += ["## 4. Current results on dev and the (fully exposed, unreviewed) candidate split", "",
            "| | Dev | Candidate |", "|---|---|---|",
            f"| Critical misses / events | {cur['dev']['headline']['critical_miss_count']} / "
            f"{cur['dev']['headline']['critical_events']} | {cur['candidate']['headline']['critical_miss_count']} / "
            f"{cur['candidate']['headline']['critical_events']} |",
            f"| False escalations | {cur['dev']['headline']['false_escalation_count']} | "
            f"{cur['candidate']['headline']['false_escalation_count']} |",
            f"| Crisis P / R | {fmt(cur['dev']['crisis']['precision'])} / {fmt(cur['dev']['crisis']['recall'])} | "
            f"{fmt(cur['candidate']['crisis']['precision'])} / {fmt(cur['candidate']['crisis']['recall'])} |",
            f"| Evidence validity | {fmt(cur['dev']['evidence']['cited_validity'])} | "
            f"{fmt(cur['candidate']['evidence']['cited_validity'])} |",
            f"| Labelled-evidence exact agreement | {fmt(cur['dev']['evidence']['evidence_exact_rate'])} | "
            f"{fmt(cur['candidate']['evidence']['evidence_exact_rate'])} |",
            f"| D4 problems | {len(cur['dev']['d4_problems'])} | {len(cur['candidate']['d4_problems'])} |", "",
            "Candidate numbers are regression numbers: every candidate outcome was published on 2026-09-11.", ""]
    out += ["## 5. Known remaining failures", "", "| Fixture | Kind | Where | Detail |", "|---|---|---|---|"]
    for f in r["remaining_failures"]:
        out.append(f"| `{f['id']}` | {f['kind']} | {f['split']} | {f['actual']} |")
    inv = r["invariants"]
    c = r["checks"]
    out += ["", "## 6. Invariants and checks", "",
            f"- SVI sensitivity sections identical to baseline: {all(inv['svi_sensitivity_unchanged'].values())} "
            f"({sum(inv['svi_sensitivity_unchanged'].values())}/{len(inv['svi_sensitivity_unchanged'])}).",
            f"- Offline: network attempts {len(c['offline']['network_attempts'])}, forbidden modules "
            f"{c['offline']['forbidden_modules_loaded'] or 'none'}, external-corpus file access "
            f"{c['external_corpus_access'] or 'none'} (files opened while the evaluation ran: {c['files_opened']}).",
            f"- Determinism: {c['determinism']['identical']}. Replay consistent: {c['scenario_replay']['consistent']}. "
            f"LLM-off completed: {c['llm_off']['completed']}.",
            f"- Static import offenders: {c['static_imports']['offenders'] or 'none'}."]
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SAHAY-AI safety-hardening report")
    parser.add_argument("--out", default=str(EVAL / "results"))
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args(argv)
    stamp = args.timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report = build(stamp)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{TAG}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                     encoding="utf-8", newline="\n")
    (out / f"{TAG}.md").write_text(render(report), encoding="utf-8", newline="\n")
    print(f"wrote {out / (TAG + '.json')} and .md; remaining failures: {len(report['remaining_failures'])}")
    return 0 if report["checks"]["offline"]["ok"] and not report["checks"]["external_corpus_access"] else 1


if __name__ == "__main__":
    sys.exit(main())
