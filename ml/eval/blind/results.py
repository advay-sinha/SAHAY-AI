"""Evaluation-result storage, validation and atomic finalization. Stdlib only.

No prediction module is imported here: this module decides where a result goes
and whether it is complete, never what is in it.

Storage, all beneath the private root
------------------------------------

    <root>/reports/<version>/
      evaluation-independent.json     the one independent result. Immutable.
      evaluation-independent.md       its human-readable companion
      exposure.json                   written at finalization; the corpus is
                                      exposed from this moment
      regression/<run_id>.json        one file per regression run
      regression/<run_id>.md
      .tmp-<run_id>/                  work in progress; never a published result

Publication is defined precisely: **a result is published the instant its JSON
file exists at its final path.** Nothing else counts. A `.md` companion, a
console line or a half-written temporary file is not publication. That
definition is what the exposure state transition is tied to.

Finalization, and what is genuinely atomic
------------------------------------------

1. write every artefact into `.tmp-<run_id>/`;
2. validate the completed result (all sections present and populated);
3. compute the result hash over the substantive content;
4. `os.replace` the artefacts into their final paths, **the JSON last**.

`os.replace` is atomic per file on both POSIX and Windows. A multi-file set is
not atomic as a group, and pretending otherwise would be a lie, so the order is
chosen to make the incomplete states harmless and detectable:

* crash before any rename -> only a temp directory exists. Nothing is
  published, nothing is exposed, the next run deletes the temp directory and
  starts again.
* crash after the `.md` rename but before the JSON -> a stray `.md` with no
  JSON. By the definition above nothing is published; the next run overwrites
  the `.md` and the state is unchanged. `pending_artefacts` reports it.
* crash after the JSON rename but before the exposure record is appended ->
  the result IS published, and the corpus IS exposed, but the ledger does not
  say so yet. This is the one window that needs repair rather than retry:
  `unrecorded_publication` detects it, and the caller re-appends the exposure
  record from the published result instead of re-running the pipeline. A
  published independent result is never recomputed.

A finalized independent result is never overwritten. `finalize` refuses if the
target exists, so a second independent run cannot replace the first even if
somebody deletes the exposure record.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

RESULT_VERSION = "1.0.0"

INDEPENDENT = "independent_evaluation"
REGRESSION = "regression_after_exposure"
INDEPENDENCE_VALUES = (INDEPENDENT, REGRESSION)

#: Sections a complete result must carry. Fixed so the report format cannot drift.
REQUIRED_SECTIONS = (
    "detector_metrics",
    "by_language",
    "by_category",
    "by_challenge_slice",
    "label_slices",
    "critical_misses",
    "false_escalations",
    "abstention",
    "evidence_link_validity",
    "routing_labels",
    "svi_distribution",
    "determinism",
    "scenario_replay",
    "guardrail_prohibition_coverage",
)

#: Top-level keys a complete result must carry.
REQUIRED_TOP_LEVEL = ("result_version", "run_id", "run_at", "run_by", "independence", "corpus",
                      "ledger_heads", "versions", "derived_expectations", "sections")

#: Metadata that legitimately differs between two runs of the same corpus and
#: is therefore excluded from the determinism and regression comparisons. Every
#: other field is substantive and must match exactly.
NON_SUBSTANTIVE = ("run_id", "run_at", "run_by", "independence", "compared_to", "result_sha256")

INDEPENDENT_STEM = "evaluation-independent"
EXPOSURE_FILE = "exposure.json"
TEMP_PREFIX = ".tmp-"


class ResultError(Exception):
    """A result is incomplete, or a finalized result would be overwritten."""


def _remove_tree(path: Path) -> None:
    """Delete a temporary run directory, depth first.

    Written with ``os`` rather than ``shutil`` on purpose: ``ml/`` forbids
    importing ``shutil``, ``zipfile``, ``tarfile`` and ``gzip`` outside the
    dataset-governance package, and ``ml/tests/test_hardening.py`` enforces it.
    Nothing in the evaluation path should be able to touch an archive, and the
    cheapest way to guarantee that is not to import the tools that can.
    """
    path = Path(path)
    if not path.is_dir():
        return
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            try:
                os.remove(os.path.join(root, name))
            except OSError:
                pass
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def substantive(result: Mapping[str, Any]) -> Dict[str, Any]:
    """The part of a result that two runs of the same corpus must share."""
    return {k: v for k, v in result.items() if k not in NON_SUBSTANTIVE}


def result_sha256(result: Mapping[str, Any]) -> str:
    """Hash over the substantive content only."""
    return hashlib.sha256(canonical(substantive(result)).encode("utf-8")).hexdigest()


def validate_result(result: Mapping[str, Any]) -> List[str]:
    """Problems that make a result unpublishable. Empty means complete."""
    errs: List[str] = []
    if not isinstance(result, Mapping):
        return ["result must be a JSON object"]
    for key in REQUIRED_TOP_LEVEL:
        if key not in result:
            errs.append(f"missing top-level key {key!r}")
    if errs:
        return errs
    if result["result_version"] != RESULT_VERSION:
        errs.append(f"result_version must be {RESULT_VERSION}")
    if result["independence"] not in INDEPENDENCE_VALUES:
        errs.append(f"independence must be one of {INDEPENDENCE_VALUES}")
    sections = result["sections"]
    if not isinstance(sections, Mapping):
        return errs + ["sections must be an object"]
    for name in REQUIRED_SECTIONS:
        if name not in sections:
            errs.append(f"missing section {name!r}")
        elif sections[name] is None or sections[name] == {} or sections[name] == []:
            errs.append(f"section {name!r} is empty")
    for key in ("corpus_version", "corpus_sha256", "freeze_manifest_sha256", "samples"):
        if key not in (result["corpus"] or {}):
            errs.append(f"corpus block is missing {key!r}")
    if (result["corpus"] or {}).get("samples", 0) < 1:
        errs.append("a result over zero samples is not a result")
    for key in ("pipeline_version", "scoring_version", "lexicon_version", "validator_version"):
        if key not in (result["versions"] or {}):
            errs.append(f"versions block is missing {key!r}")
    determinism = sections.get("determinism") or {}
    if determinism.get("identical") is not True:
        errs.append("the pipeline was not deterministic across repeat runs; the result is not publishable")
    return errs


# --- paths ------------------------------------------------------------------------------


def reports_dir(store: Any) -> Path:
    return store.path("reports")


def temp_dir(store: Any, run_id: str) -> Path:
    return reports_dir(store) / f"{TEMP_PREFIX}{run_id}"


def independent_json(store: Any) -> Path:
    return reports_dir(store) / f"{INDEPENDENT_STEM}.json"


def independent_md(store: Any) -> Path:
    return reports_dir(store) / f"{INDEPENDENT_STEM}.md"


def regression_json(store: Any, run_id: str) -> Path:
    return reports_dir(store) / "regression" / f"evaluation-regression-{run_id}.json"


def regression_md(store: Any, run_id: str) -> Path:
    return reports_dir(store) / "regression" / f"evaluation-regression-{run_id}.md"


def exposure_path(store: Any) -> Path:
    return store.path("frozen", EXPOSURE_FILE)


def published_independent(store: Any) -> Optional[Dict[str, Any]]:
    """The published independent result, or None. Publication == this file exists."""
    path = independent_json(store)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise ResultError("the published independent result is not valid JSON") from None


def exposure_record(store: Any) -> Optional[Dict[str, Any]]:
    path = exposure_path(store)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise ResultError("the exposure record is not valid JSON") from None


def unrecorded_publication(store: Any) -> bool:
    """A published independent result whose exposure record never landed.

    This is the one interrupted state that must be repaired rather than
    retried: the corpus is already exposed, so re-running the pipeline would
    not restore independence, and the published result must not be recomputed.
    """
    return published_independent(store) is not None and exposure_record(store) is None


def pending_artefacts(store: Any) -> List[str]:
    """Temporary directories and orphaned companions left by interrupted runs."""
    reports = reports_dir(store)
    if not reports.is_dir():
        return []
    stray = [p.name for p in sorted(reports.iterdir())
             if p.is_dir() and p.name.startswith(TEMP_PREFIX)]
    if independent_md(store).is_file() and not independent_json(store).is_file():
        stray.append(f"{INDEPENDENT_STEM}.md (companion with no published result)")
    return stray


def clean_temp(store: Any) -> List[str]:
    """Delete every temporary run directory. Never touches a final artefact."""
    reports = reports_dir(store)
    removed: List[str] = []
    if not reports.is_dir():
        return removed
    for path in sorted(reports.iterdir()):
        if path.is_dir() and path.name.startswith(TEMP_PREFIX):
            _remove_tree(path)
            removed.append(path.name)
    return removed


# --- finalization -----------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def finalize(store: Any, run_id: str, result: Mapping[str, Any], markdown: str,
             independent: bool) -> Dict[str, Any]:
    """Validate, hash and atomically publish one result. Returns its paths and hash."""
    errs = validate_result(result)
    if errs:
        raise ResultError("the result is incomplete and was not published: " + "; ".join(errs))
    want_label = INDEPENDENT if independent else REGRESSION
    if result["independence"] != want_label:
        raise ResultError(f"result is labelled {result['independence']!r} but is being published as "
                          f"{want_label!r}")

    final_json = independent_json(store) if independent else regression_json(store, run_id)
    final_md = independent_md(store) if independent else regression_md(store, run_id)
    if independent and final_json.exists():
        raise ResultError("an independent result is already published for this corpus version; "
                          "it is never overwritten")
    if final_json.exists():
        raise ResultError(f"a result already exists at {final_json.name}")

    digest = result_sha256(result)
    stamped = dict(result)
    stamped["result_sha256"] = digest

    work = temp_dir(store, run_id)
    _remove_tree(work)
    work.mkdir(parents=True, exist_ok=True)
    tmp_json = _write(work / final_json.name,
                      json.dumps(stamped, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    tmp_md = _write(work / final_md.name, markdown)

    # Re-read what was actually written before anything is published.
    written = json.loads(tmp_json.read_text(encoding="utf-8"))
    if validate_result(written) or result_sha256(written) != digest:
        _remove_tree(work)
        raise ResultError("the written result did not validate; nothing was published")

    final_json.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp_md, final_md)      # companion first
    os.replace(tmp_json, final_json)  # publication happens here, and only here
    _remove_tree(work)
    return {"json": final_json, "md": final_md, "result_sha256": digest, "run_id": run_id}


def record_exposure(store: Any, run_id: str, result_hash: str, actor: Mapping[str, Any],
                    at: str) -> Dict[str, Any]:
    """Write the exposure record. Called only after a published independent result."""
    record = {
        "corpus_version": store.version,
        "exposed": True,
        "exposed_at": at,
        "exposed_by": {k: actor.get(k) for k in ("person_id", "identity", "role")},
        "by_run_id": run_id,
        "result_sha256": result_hash,
        "reason": "the independent evaluation result for this corpus version has been published; "
                  "every sample in it is now a regression fixture",
    }
    _write(exposure_path(store), json.dumps(record, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def compare(original: Mapping[str, Any], candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Substantive comparison of a regression result against the independent one."""
    base, new = substantive(original), substantive(candidate)
    changed = sorted({k for k in set(base) | set(new) if base.get(k) != new.get(k)})
    sections_changed: List[str] = []
    if "sections" in changed:
        old_s = base.get("sections") or {}
        new_s = new.get("sections") or {}
        sections_changed = sorted({k for k in set(old_s) | set(new_s) if old_s.get(k) != new_s.get(k)})
    return {
        "original_run_id": original.get("run_id"),
        "original_result_sha256": original.get("result_sha256"),
        "candidate_result_sha256": result_sha256(candidate),
        "identical": not changed,
        "changed_top_level": changed,
        "changed_sections": sections_changed,
        "note": "A difference here is a behaviour change since the independent run. It is regression "
                "information: the independent number is the one that was measured before anyone looked.",
    }
