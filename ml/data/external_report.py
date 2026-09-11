"""Composition report for private external research data. Stdlib only.

    python -m ml.data.external_report [--root R] [--out DIR]

Describes what the external development data IS — counts, languages, scripts,
source-label distributions, splits, duplicates, privacy findings, overlap with
exposed SAHAY corpora, exclusions and governance state — without running,
scoring or tuning the pipeline. It reads only:

  * the registry;
  * private normalised records and manifests written by
    ``external_corpus.convert`` (streamed, never held whole in memory).

It never reads a raw source file. Output goes to
``<SAHAY_DATASETS_ROOT>/reports/external-report/`` and holds ids, counts and
hashes only. Without a dataset root the registry-only view is printed and
nothing is written.

Wording
-------
A pipeline run over external data is labelled ``external_exploratory_analysis``
and reports exploratory firing rates only.
Neither that output nor this report may describe itself with the words listed
in ``FORBIDDEN_WORDS``; ``assert_wording`` enforces it on everything written.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from . import external_corpus as xc
from . import governance as gov
from . import label_firewall as fw

REPORT_LABEL = "external_exploratory_composition"
ANALYSIS_LABEL = "external_exploratory_analysis"
#: Words the report and any external exploratory analysis may never use.
FORBIDDEN_WORDS = ("official", "independent", "validated", "clinical accuracy", "production accuracy",
                   "locked-set performance")
_FORBIDDEN = [re.compile(r"\b" + r"\s+".join(re.escape(part) for part in w.split()) + r"\b", re.IGNORECASE)
              for w in FORBIDDEN_WORDS]


class WordingError(Exception):
    """A report tried to describe external development data with forbidden wording."""


def assert_wording(text: str) -> None:
    hits = sorted({p.pattern for p in _FORBIDDEN if p.search(text)})
    if hits:
        raise WordingError(f"forbidden wording in an external development report ({len(hits)} term(s))")


def _sorted(counter: Counter) -> Dict[str, int]:
    return {str(k): v for k, v in sorted(counter.items(), key=lambda kv: str(kv[0]))}


def composition(records: Iterable[Mapping[str, Any]], keys: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Streaming aggregates over normalised records. No text: ids, counts and categories.

    If ``keys`` is given, each record's duplicate keys are appended to it for
    the cross-dataset overlap check.
    """
    c: Dict[str, Counter] = {k: Counter() for k in (
        "languages", "language_basis", "scripts", "source_splits", "labels", "families", "privacy",
        "contamination", "matched", "duplicates", "governance")}
    n = dialogues = with_privacy = mapping_needed = locked = d4 = 0
    for r in records:
        n += 1
        dialogues += bool(r.get("turns"))
        c["languages"][r["language"]] += 1
        c["language_basis"][r["language_basis"]] += 1
        c["scripts"][r["script"]] += 1
        c["source_splits"][r["source_split"]] += 1
        for cat in r.get("source_label_category") or ["source:_unlabelled"]:
            c["labels"][cat] += 1
        for fam in r.get("source_label_family") or []:
            c["families"][fam] += 1
        if r.get("privacy_findings"):
            with_privacy += 1
        for f in r.get("privacy_findings") or []:
            c["privacy"][f["rule"]] += int(f["count"])
        c["contamination"][r["contamination"]["status"]] += 1
        for f in r["contamination"]["findings"]:
            c["matched"][f["matched_id"]] += 1
        if r.get("duplicate_kind"):
            c["duplicates"][r["duplicate_kind"]] += 1
        c["governance"][r.get("governance_basis", "unknown")] += 1
        mapping_needed += not r["sahay_mapping"]["applied"]
        locked += bool(r["locked_corpus_eligible"])
        d4 += bool(r["d4"]["available"])
        if keys is not None:
            keys.append({"record_id": r["record_id"], "exact_key": r.get("exact_key"), "near_key": r.get("near_key")})
    return {
        "records": n,
        "dialogue_records": dialogues,
        "languages": _sorted(c["languages"]),
        "language_basis": _sorted(c["language_basis"]),
        "scripts": _sorted(c["scripts"]),
        "source_splits": _sorted(c["source_splits"]),
        "source_label_categories": _sorted(c["labels"]),
        "source_label_families": _sorted(c["families"]),
        "duplicates": {"exact": c["duplicates"]["exact"], "near": c["duplicates"]["near"]},
        "privacy_findings_by_rule": _sorted(c["privacy"]),
        "records_with_privacy_findings": with_privacy,
        "contamination": _sorted(c["contamination"]),
        "contamination_matched_ids": sorted(c["matched"]),
        "governance_basis": _sorted(c["governance"]),
        "records_requiring_human_mapping": mapping_needed,
        "locked_corpus_eligible": locked,
        "d4_available": d4,
    }


def build(root: Optional[Path], registry: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    reg = registry if registry is not None else gov.load_registry()
    rows: List[Dict[str, Any]] = []
    all_keys: Dict[str, List[Dict[str, Any]]] = {}
    for rec in reg["datasets"]:
        row: Dict[str, Any] = {
            "dataset_id": rec["id"], "review_status": rec["review_status"],
            "download_status": rec["download_status"], "ext_decision": rec["ext_decision"],
            "licence_name": rec["licence_name"], "redistribution": rec["redistribution"],
            "commercial_use": rec["commercial_use"], "approved_uses": rec["approved_uses"],
            "prohibited_uses": rec["prohibited_uses"], "governance_gaps": gov.governance_gaps(rec),
            "adapter_spec": rec["id"] in xc.SPECS,
            "adapter_ontology_verified": bool(xc.SPECS.get(rec["id"], {}).get("ontology_verified")),
        }
        try:
            gov.select_for(reg, rec["id"], "research")
            row["conversion_permitted_by_registry"] = True
        except gov.GovernanceError as exc:
            row["conversion_permitted_by_registry"] = False
            row["registry_refusal"] = str(exc)
        row["local_research_override_eligible"] = (rec["review_status"] in xc.OVERRIDE_ELIGIBLE_STATES
                                                   and rec["download_status"] == "downloaded")
        row["sensitivity_flags"] = list(rec.get("sensitivity_flags") or [])
        stream = xc.iter_normalized(root, rec["id"], reg) if root is not None else None
        if stream is not None:
            keys: List[Dict[str, Any]] = []
            row["composition"] = composition(stream, keys)
            all_keys[rec["id"]] = keys
            manifest = xc.load_manifest(root, rec["id"], reg) or {}
            row["manifest"] = {k: manifest.get(k) for k in ("source_rows_read", "units_discovered", "unit",
                                                            "records", "excluded", "source_file",
                                                            "records_sha256", "governance_basis", "processing",
                                                            "artifact_class")}
            row["status"] = "converted"
        else:
            row["status"] = "not_converted"
        rows.append(row)
    return {
        "report": REPORT_LABEL,
        "analysis_label": ANALYSIS_LABEL,
        "pipeline_run": False,
        "tuning_performed": False,
        "datasets": rows,
        "cross_dataset_overlap": xc.cross_dataset_overlap(all_keys),
        "label_firewall": {"version": fw.FIREWALL_VERSION, "authorised_mappings": list(fw.AUTHORISED_MAPPINGS),
                           "refusals": fw.refusals()},
        "statement": "Private exploratory research composition. External records are quarantined research "
                     "artefacts: they cannot enter the product or demo, are not blind-authored, are never eligible "
                     "for the locked corpus, carry source labels made for other tasks, and have not been mapped to "
                     "any SAHAY label, band, SVI dimension, routing decision or D4 value. Rule-based redaction "
                     "cannot detect personal names, places or contextual identifiers. No pipeline was run for this "
                     "report and nothing was tuned.",
        "retention_recommendation": xc.RETENTION_RECOMMENDATION,
    }


def render(report: Mapping[str, Any]) -> str:
    out = ["# Private exploratory research composition (external data)", "",
           f"Label: `{report['report']}` · pipeline run: {report['pipeline_run']} · "
           f"tuning performed: {report['tuning_performed']}", "",
           report["statement"], "",
           "| Dataset | Review state | Registry permits | Research override eligible | Sensitivity | Status | Rows | "
           "Records | Excluded |",
           "|---|---|---|---|---|---|---:|---:|---:|"]
    for r in report["datasets"]:
        m = r.get("manifest") or {}
        out.append(f"| `{r['dataset_id']}` | {r['review_status']} | {r['conversion_permitted_by_registry']} | "
                   f"{r['local_research_override_eligible']} | {', '.join(r['sensitivity_flags']) or '—'} | "
                   f"{r['status']} | {m.get('source_rows_read', '—')} | "
                   f"{m.get('records', '—')} | {sum((m.get('excluded') or {}).values()) if m else '—'} |")
    for r in report["datasets"]:
        comp = r.get("composition")
        if not comp:
            continue
        out += ["", f"## `{r['dataset_id']}`", "",
                f"- governance basis {comp['governance_basis']}; processing {r['manifest'].get('processing')}",
                f"- exclusions {r['manifest'].get('excluded')}",
                f"- records {comp['records']} (dialogues {comp['dialogue_records']})",
                f"- languages {comp['languages']} ({comp['language_basis']})",
                f"- scripts {comp['scripts']}",
                f"- source splits {comp['source_splits']}",
                f"- source labels {comp['source_label_categories']}",
                f"- duplicates {comp['duplicates']}",
                f"- privacy redactions {comp['privacy_findings_by_rule']} "
                f"({comp['records_with_privacy_findings']} record(s))",
                f"- overlap with exposed SAHAY corpora {comp['contamination']} "
                f"(matched ids {comp['contamination_matched_ids'][:20]})",
                f"- requiring human mapping {comp['records_requiring_human_mapping']} · "
                f"locked-corpus eligible {comp['locked_corpus_eligible']} · D4 available {comp['d4_available']}",
                f"- normalised output sha256 `{r['manifest'].get('records_sha256')}`"]
    out += ["", "## Cross-dataset overlap", "",
            f"{len(report['cross_dataset_overlap'])} shared exact or near key(s).", "",
            "## Source-label firewall", "",
            f"Authorised mappings: {len(report['label_firewall']['authorised_mappings'])}.", ""]
    for rule, why in report["label_firewall"]["refusals"].items():
        out.append(f"- `{rule}`: {why}")
    text = "\n".join(out) + "\n"
    assert_wording(text)
    return text


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Private exploratory research composition report (external data)")
    parser.add_argument("--root", default=None, help=f"dataset root (default: ${gov.ROOT_ENV}; optional)")
    parser.add_argument("--out", default=None, help="default: <root>/reports/external-report")
    args = parser.parse_args(argv)
    try:
        root: Optional[Path] = gov.dataset_root(args.root)
    except gov.DatasetRootError:
        root = None
    report = build(root)
    text = render(report)
    blob = json.dumps(report, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    assert_wording(blob)
    permitted = sum(1 for r in report["datasets"] if r["conversion_permitted_by_registry"])
    converted = sum(1 for r in report["datasets"] if r["status"] == "converted")
    if args.out:
        out = Path(args.out)
        if xc.inside_sahay_worktree(out):
            print("configuration: refusing to write an external report inside a SAHAY Git worktree")
            return 4
    elif root is not None:
        out = xc.reports_dir(root, "external-report")
    else:
        print(f"{len(report['datasets'])} registered dataset(s); registry permits {permitted}; converted "
              f"{converted}; no dataset root, so nothing was written")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(blob, encoding="utf-8", newline="\n")
    (out / "report.md").write_text(text, encoding="utf-8", newline="\n")
    retention = write_retention_recommendation(root) if root is not None else None
    print(f"{len(report['datasets'])} registered dataset(s); registry permits {permitted}; converted {converted}; "
          f"written to the private reports directory"
          + (f"; retention recommendation covers {len(retention['outputs'])} output(s)" if retention else ""))
    return 0


def retention_recommendation(root: Path) -> Dict[str, Any]:
    """What sensitive normalised text exists, and when it should go. Deletes nothing.

    Paths are relative to ``<SAHAY_DATASETS_ROOT>``; the record lives in the
    private reports directory and is never committed.
    """
    base = gov.resolve_under(Path(root), "normalized")
    outputs: List[Dict[str, Any]] = []
    if base.is_dir():
        for manifest in sorted(base.glob("*/*/manifest.json")):
            try:
                m = json.loads(manifest.read_text(encoding="utf-8"))
            except ValueError:
                m = {}
            records = manifest.parent / "records.jsonl"
            outputs.append({
                "relative_path": manifest.parent.relative_to(base.parent).as_posix(),
                "dataset_id": m.get("dataset_id"),
                "records": m.get("records"),
                "bytes": records.stat().st_size if records.is_file() else 0,
                "artifact_class": m.get("artifact_class", xc.ARTIFACT_CLASS),
                "governance_basis": m.get("governance_basis"),
                "recommendation": xc.RETENTION_RECOMMENDATION,
            })
    return {
        "record": "private retention recommendation for quarantined research artefacts",
        "root": "<" + gov.ROOT_ENV + ">",
        "automatic_deletion": False,
        "policy": [
            "Retain the normalised text only while this analysis is actively required.",
            "Delete the normalised sensitive text once aggregate review is complete; keep only the aggregate reports.",
            "Never commit this record, any normalised output or any machine path.",
            "Rule-based redaction cannot detect personal names, places or contextual identifiers that may remain.",
        ],
        "outputs": outputs,
        "total_bytes": sum(o["bytes"] for o in outputs),
    }


def write_retention_recommendation(root: Path) -> Dict[str, Any]:
    record = retention_recommendation(root)
    out = xc.reports_dir(root, "retention")
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "retention-recommendation.json.partial"
    tmp.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, out / "retention-recommendation.json")
    return record


if __name__ == "__main__":
    sys.exit(main())
