"""Judge-defence pages generated from result files (plan M16). No number is typed by hand.

    python -m ml.eval.defence --eval-json ml/eval/results/eval-2026-09-28.json \\
        --table-json ml/eval/results/eval-table-2026-09-29.json --out docs/defence

It writes two pages:
- ``RED_TEAM.md``: the red-team result by category, language and severity;
- ``NUMBERS.md``: headline numbers per language (routing, crisis pre-check, detectors) plus the
  measured rows of the evaluation table, each with its evidence class.

Aggregates only: no fixture text, no transcript. Every page passes the evaluation-table wording
guard, and "official" never appears while the locked set is empty.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .table import check_wording

LANG_NAMES = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish"}
SPLITS = (("dev", "exposed development"), ("candidate", "exposed candidate"))


def _pct(k: int, n: int) -> str:
    return f"{k}/{n}" if n else "—"


def _f(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.2f}"


def red_team(report: Mapping[str, Any]) -> str:
    rt = report["redteam"]
    out = [
        "# Red-team result",
        "",
        f"Generated from the evaluation run of {report.get('timestamp', '—')} "
        f"(commit `{(report.get('git') or {}).get('commit', '—')[:12]}`).",
        "",
        "**Evidence class: exposed regression.** The red-team corpus was published on 2026-09-11 and "
        "its failures were fixed afterwards, so a pass shows the regression is fixed, not that the "
        "validator generalises (`ml/eval/CONTAMINATION.md`).",
        "",
        f"**{rt['passed']} of {rt['cases']} cases blocked before synthesis.** Failures by severity: "
        + ", ".join(f"{k} {v}" for k, v in sorted(rt.get("failures_by_severity", {}).items())) + ".",
        "",
        "## By language",
        "",
        "| Language | Cases | Blocked |",
        "|---|---|---|",
    ]
    for lang, s in sorted(rt.get("by_language", {}).items()):
        out.append(f"| {LANG_NAMES.get(lang, lang)} | {s['cases']} | {_pct(s['passed'], s['cases'])} |")
    out += ["", "## By category", "", "| Category | Cases | Blocked | Languages |", "|---|---|---|---|"]
    for cat, s in sorted(rt.get("by_category", {}).items()):
        langs = ", ".join(LANG_NAMES.get(x, x) for x in s.get("languages", []))
        out.append(f"| {cat.replace('_', ' ')} | {s['cases']} | {_pct(s['passed'], s['cases'])} | {langs} |")
    out += ["", "Hindi has the fewest red-team cases. More Hindi and Hinglish cases, written by people who "
            "did not build the validator, are needed before any claim about those languages.", ""]
    return "\n".join(out)


def per_language(report: Mapping[str, Any]) -> List[str]:
    out = ["## Safety routing by language", "",
           "Crisis pre-check recall and critical-event misses per language. Small n: read every rate with "
           "its denominator.", "",
           "| Split | Language | n | Critical events missed | Crisis pre-check recall | Crisis pre-check precision |",
           "|---|---|---|---|---|---|"]
    for split, label in SPLITS:
        result = (report["splits"].get(split) or {}).get("result") or {}
        for lang, pl in sorted((result.get("per_language") or {}).items()):
            rt = pl.get("routing", {})
            miss = rt.get("critical_event_miss_rate", {})
            pre = rt.get("crisis_precheck", {})
            out.append(f"| {label} | {LANG_NAMES.get(lang, lang)} | {pl.get('n', '—')} | "
                       f"{_pct(miss.get('missed', 0), miss.get('critical_events', 0))} | "
                       f"{_pct(pre.get('tp', 0), pre.get('recall_denominator', 0))} | "
                       f"{_pct(pre.get('tp', 0), pre.get('precision_denominator', 0))} |")
    return out + [""]


def numbers(report: Mapping[str, Any], table: Mapping[str, Any]) -> str:
    locked = int(table.get("locked_samples") or 0)
    out = ["# Headline numbers", "",
           f"Generated from `{table.get('eval_source') or '—'}` and evaluation table `{table.get('table_version')}`. "
           f"Locked-set metrics: **pending** ({locked} locked samples). Every number below names its evidence class; "
           "`pending` means not measured, never zero.", ""]
    out += per_language(report)
    groups = (("Safety routing and red-team", ("M1", "M1a", "M1b", "M1c", "M1d", "M5")),
              ("Turn latency (M2)", ("M2",)),
              ("Speech emotion, shadow (selected rows)", ("SER",)),
              ("Text affect, shadow", ("TXT",)),
              ("Shadow safety detector, Stage W", ("SHD",)),
              ("Interpretable baseline, AE-15", ("AE15",)))
    rows = table["rows"]
    for title, ids in groups:
        picked = [r for r in rows if r["metric_id"] in ids and r["status"] == "measured"]
        if title.startswith("Speech"):
            picked = [r for r in picked if r["scope"].startswith("test:") and ("both" in r["metric"])]
        if not picked:
            continue
        out += [f"## {title}", "", "| Metric | Scope | Value | 95% CI | n | Evidence |", "|---|---|---|---|---|---|"]
        for r in picked:
            ci = f"[{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]" if r.get("ci95") else "—"
            v = r["value"]
            val = f"{v:.3f}" if isinstance(v, float) and v <= 1.5 else f"{v}"
            out.append(f"| {r['metric']} | {r['scope']} | {val} | {ci} | {r.get('n') or '—'} | {r['evidence_class']} |")
        out.append("")
    pending = [r for r in rows if r["status"] in ("pending", "unvalidated", "not_available")]
    out += ["## Not measured yet", ""] + [f"- **{r['metric_id']}** {r['metric']} ({r['scope']}): {r['status']}"
                                          + (f", {r['note']}" if r.get("note") else "") for r in pending] + [""]
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Judge-defence pages from result files")
    parser.add_argument("--eval-json", required=True)
    parser.add_argument("--table-json", required=True)
    parser.add_argument("--out", default="docs/defence")
    args = parser.parse_args(argv)
    report = json.loads(Path(args.eval_json).read_text(encoding="utf-8"))
    table = json.loads(Path(args.table_json).read_text(encoding="utf-8"))
    locked = int(table.get("locked_samples") or 0)
    pages: Dict[str, str] = {"RED_TEAM.md": red_team(report), "NUMBERS.md": numbers(report, table)}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in pages.items():
        check_wording(text, locked)
        (out / name).write_text(text, encoding="utf-8")
        print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
