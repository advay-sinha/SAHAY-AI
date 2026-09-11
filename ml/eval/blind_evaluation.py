"""The one-time official evaluation on a frozen blind corpus. Stdlib only.

    python -m ml.eval.blind_evaluation run --root "$env:SAHAY_EVAL_ROOT" --version v1
    python -m ml.eval.blind_evaluation run --regression --actor person-001
    python -m ml.eval.blind_evaluation status
    python -m ml.eval.blind_evaluation clean-temp

With no frozen corpus this REFUSES with exit code 12, which is the state of
the repository today: nothing has been authored, reviewed and frozen, so no
official number exists. Given a frozen corpus it runs the existing
deterministic pipeline and publishes a complete result.

Precondition sequence, in this exact order
------------------------------------------
Steps 1-8 run with **no prediction module loaded**. Each refuses before the
next is attempted, so a configuration mistake can never reach the pipeline.

  1. resolve the version strictly beneath ``SAHAY_EVAL_ROOT``      (exit 2)
  2. validate configuration: roster-free, root exists, version shape (exit 2)
  3. a freeze manifest exists for this version                     (exit 12)
  4. the manifest's corpus_version matches the requested version   (exit 10)
  5. the corpus hash and every per-file hash verify                (exit 10)
  6. the four recorded ledger heads verify                         (exit 10)
  7. every frozen sample is in the state this run requires         (exit 14)
  8. the corpus has not already been evaluated as independent
     evidence (unless ``--regression`` is given)                   (exit 2)

  9. only now: ``_pipeline()`` imports the assessment pipeline, the evaluator
     and the offline checks. That function is the ONLY import boundary, and
     ``ml/tests/test_blind_evaluation.py`` proves each refusal above leaves
     ``sys.modules`` free of every forbidden module.

 10-14. run predictions, compute the report, verify a repeat run is identical,
     publish atomically, then record exposure and move the samples.

Routing label, SVI band and abstention are three different things
-----------------------------------------------------------------
The reviewers annotate a ROUTING LABEL: what should happen, who is woken up and
how fast. The pipeline emits an SVI BAND: what the deterministic scorer output.
"Needs Human Assessment" is neither — it means no score was produced at all.
They share the vocabulary `Low | Moderate | High | Critical` and nothing else.

So this report compares predicted routing only against the human routing label
(thresholded at Critical, which is the only routing decision the pipeline
actually makes), reports the band distribution descriptively, counts Needs
Human Assessment separately from the scored bands, and computes NO band
accuracy: no human ever labelled a band, and inventing one from the routing
label would publish a number measured against a different question.

Reuse
-----
Nothing here re-implements a detector, the SVI, a threshold, an override or an
abstention rule. It calls ``ml.eval.predict.predict``, ``ml.eval.evaluate``'s
own tables, ``ml.eval.metrics``, ``ml.eval.checks.determinism`` and
``scenario_replay``, and ``ml.eval.redteam.prohibition_coverage`` — the same
code paths ``run_eval`` uses. The only new logic is the adapter
(``blind/adapter.py``), the extra metric cuts the blind coverage plan needs,
and result finalization (``blind/results.py``). The command exposes no
threshold, weight or lexicon option: tuning through this path is impossible by
construction, not by policy.

Independence
------------
The first successful run on a frozen corpus is labelled
``independent_evaluation``. Publishing it — which means the JSON result file
existing at its final path — exposes the corpus: every sample becomes a
regression fixture, the samples move ``frozen -> evaluated ->
contaminated_after_evaluation``, and an exposure record is written. Any later
run needs ``--regression``, is labelled ``regression_after_exposure``, is
written to its own uniquely named file, is compared against the independent
result, and can never overwrite it. A failed or interrupted run changes no
state. See ``ml/eval/BLIND_EVALUATION.md``.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .blind import firewall
from .blind import results as rs
from .blind.adapter import (ADAPTER_VERSION, BAND_GROUND_TRUTH_AVAILABLE,
                           BAND_GROUND_TRUTH_REASON, DERIVED_EXPECTATIONS, adapt_all,
                           validate_all)
from .blind.exit_codes import (EXIT_EVALUATION_FAILED, EXIT_LEDGER, EXIT_NO_FROZEN_CORPUS, EXIT_OK,
                               EXIT_STATE, EXIT_USAGE)
from .blind.freeze import verify_frozen
from .blind.ledger import LedgerError
from .blind.paths import ROOT_ENV, RootError, check_version
from .blind.plan import CATEGORY_NAMES, SLICE_NAMES, categories_of
from .blind.states import StateError
from .blind.store import Store, StoreError

RUN_VERSION = "1.0.0"

#: Kept for callers that imported the earlier name.
REQUIRED_SECTIONS = rs.REQUIRED_SECTIONS

#: States the frozen samples must be in for each kind of run.
STATES_FOR_INDEPENDENT = ("frozen",)
STATES_FOR_REGRESSION = ("frozen", "evaluated", "contaminated_after_evaluation")
#: States a sample can only be in because an evaluation already happened.
STATES_AFTER_EVALUATION = ("evaluated", "contaminated_after_evaluation")

ALREADY_EVALUATED_MESSAGE = (
    "this corpus has already been evaluated and its outcomes are exposed; a further run is a "
    "regression run and must be asked for with --regression. The independent result is kept and is "
    "never overwritten.")


class EvaluationError(Exception):
    """The evaluation refused to run, or the run failed. Carries an exit code."""

    def __init__(self, message: str, code: int = EXIT_EVALUATION_FAILED):
        super().__init__(message)
        self.code = code


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_id_for(corpus_sha256: str, at: str) -> str:
    """A unique, non-substantive run id. Excluded from every comparison."""
    return hashlib.sha256(f"{corpus_sha256}|{at}".encode("utf-8")).hexdigest()[:16]


# --- steps 1-8: preconditions, with no prediction module loaded --------------------------


def preflight(store: Store, regression: bool) -> Dict[str, Any]:
    """Steps 3-8. Raises on the first failure. Imports nothing that can predict."""
    # 3. a frozen corpus exists
    manifest = store.frozen_manifest()
    if manifest is None:
        raise EvaluationError(
            f"no frozen corpus for version {store.version}: nothing has been authored, reviewed and "
            "frozen, so there is no independent evaluation set and no official metric exists",
            EXIT_NO_FROZEN_CORPUS)

    # 4. the manifest describes the corpus we were asked for
    if str(manifest.get("corpus_version")) != store.version:
        raise EvaluationError(
            f"the freeze manifest describes corpus version {manifest.get('corpus_version')!r}, "
            f"not {store.version!r}", EXIT_LEDGER)
    for key in ("corpus_sha256", "file_sha256", "ledger_heads", "samples"):
        if key not in manifest:
            raise EvaluationError(f"the freeze manifest is incomplete: no {key!r}", EXIT_LEDGER)
    if not manifest["samples"]:
        raise EvaluationError("the freeze manifest records zero samples", EXIT_LEDGER)

    # 5 + 6. corpus hash, per-file hashes and the four recorded ledger heads
    problems = verify_frozen(store)
    if problems:
        raise EvaluationError("the frozen corpus does not verify: " + "; ".join(problems), EXIT_LEDGER)

    corpus = store.read_frozen("corpus")
    labels = store.read_frozen("labels")
    ids = [str(row["submission_id"]) for row in corpus]
    if len(ids) != manifest["samples"]:
        raise EvaluationError("the frozen corpus does not contain the number of samples the manifest "
                              "records", EXIT_LEDGER)

    # 7. every frozen sample is in a state this run permits
    allowed = STATES_FOR_REGRESSION if regression else STATES_FOR_INDEPENDENT
    current = store.current_states()
    wrong = sorted(sid for sid in ids if current.get(sid) not in allowed)
    already_evaluated = ALREADY_EVALUATED_MESSAGE if wrong and all(
        current.get(sid) in STATES_AFTER_EVALUATION for sid in wrong) else ""
    if wrong and not already_evaluated:
        raise EvaluationError(
            f"{len(wrong)} sample(s) are not in {allowed}: {', '.join(wrong[:10])}"
            + (" ..." if len(wrong) > 10 else ""), EXIT_STATE)

    # 8. independence. A state failure whose whole cause is a completed
    # evaluation is reported as what it is, rather than as a mystery about
    # states: the samples are post-evaluation precisely because this corpus
    # has already been spent.
    published = rs.published_independent(store)
    if (published is not None or already_evaluated) and not regression:
        raise EvaluationError(ALREADY_EVALUATED_MESSAGE, EXIT_USAGE)
    if published is None and regression:
        raise EvaluationError(
            "--regression was given but no independent result has been published for this corpus "
            "version; the first run is the independent one", EXIT_USAGE)

    return {"manifest": manifest, "corpus": corpus, "labels": labels, "ids": ids,
            "published": published, "allowed_states": allowed}


# --- step 9: the only prediction import boundary -----------------------------------------


def _pipeline() -> Dict[str, Any]:
    """Import the deterministic pipeline. Called ONLY after preflight passed.

    Deliberately a function with local imports: importing, parsing, or refusing
    for any reason never loads a prediction module. Everything returned here is
    existing repository code; nothing is re-implemented.
    """
    from ..guardrails.crisis_precheck import LEXICON_VERSION
    from ..guardrails.validator import VALIDATOR_VERSION
    from ..svi.dimensions import SCORING_VERSION
    from ..assessment import PIPELINE_VERSION
    from . import checks, redteam
    from .evaluate import _abstention, _bands, _d4, _detector_table, _evidence, _routing
    from .metrics import ratio
    from .predict import NOT_IMPLEMENTED, predict
    return {
        "predict": predict, "not_implemented": NOT_IMPLEMENTED,
        "detector_table": _detector_table, "routing": _routing, "evidence": _evidence,
        "abstention": _abstention, "bands": _bands, "d4": _d4, "ratio": ratio,
        "determinism": checks.determinism, "scenario_replay": checks.scenario_replay,
        "canonical_hash": checks.canonical_hash,
        "offline": checks.offline, "prohibition_coverage": redteam.prohibition_coverage,
        "versions": {"pipeline_version": PIPELINE_VERSION, "scoring_version": SCORING_VERSION,
                     "lexicon_version": LEXICON_VERSION, "validator_version": VALIDATOR_VERSION,
                     "adapter_version": ADAPTER_VERSION, "run_version": RUN_VERSION},
    }


# --- steps 10-11: predictions and metrics ------------------------------------------------


def _cut(pipe: Mapping[str, Any], samples: Sequence[Mapping[str, Any]],
         preds: Mapping[str, Any], subset: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """One metric block for a subset, reusing the evaluator's own tables.

    ``preds`` is computed once for the whole corpus and shared, so a slice cut
    never re-runs the pipeline and can never disagree with the headline.
    """
    return {
        "n": len(subset),
        "sample_ids": sorted(str(s["id"]) for s in subset),
        "detectors": pipe["detector_table"](subset, preds) if subset else {},
        "routing": pipe["routing"](subset, preds) if subset else {},
    }


def measure(store: Store, pre: Mapping[str, Any], pipe: Mapping[str, Any]) -> Dict[str, Any]:
    """Run the pipeline over the frozen corpus and build every required section."""
    samples = adapt_all(pre["corpus"], pre["labels"])
    errs = validate_all(samples)
    if errs:
        raise EvaluationError("the frozen corpus does not adapt to the evaluator schema: "
                              + "; ".join(errs[:10]), EXIT_EVALUATION_FAILED)

    predict = pipe["predict"]
    preds = {s["id"]: predict(s) for s in samples}

    # 12. a repeat run of the whole prediction pass must be identical
    def rerun() -> Dict[str, Any]:
        return {s["id"]: predict(s) for s in samples}

    determinism = pipe["determinism"](rerun, runs=2)
    # the predictions the report is built from must be the ones that were proved stable
    reported_stable = pipe["canonical_hash"](preds) == determinism["sha256"]

    by_language = {lang: [s for s in samples if s["language"] == lang]
                   for lang in ("en", "hi", "hinglish")}
    label_slices = {
        "negation": [s for s in samples if s["labels"].get("negated_risk_language")],
        "quotation_attribution": [s for s in samples if s["labels"].get("quoted_attributed_risk")],
        "adversarial": [s for s in samples if s["labels"].get("adversarial_injection")],
    }
    declared = {name: [s for s in samples if name in (s.get("declared_slices") or [])]
                for name in SLICE_NAMES}
    # Coverage buckets are cut on the HUMAN ROUTING LABEL, never on a band.
    categories = {name: [s for s in samples
                         if name in categories_of(s["labels"], s["human_routing_label"],
                                                  bool(s["expected"]["abstain"]))]
                  for name in CATEGORY_NAMES}

    routing = pipe["routing"](samples, preds)
    bands = pipe["bands"](samples, preds)
    abstention = pipe["abstention"](samples, preds)
    evidence = pipe["evidence"](samples, preds)

    # The scored bands and the abstention count are kept apart on purpose:
    # "Needs Human Assessment" means no score was produced, so folding it in
    # with Low/Moderate/High/Critical would turn an abstention into a verdict.
    needs_human = bands["distribution"].get("Needs Human Assessment", 0)
    scored_bands = {band: count for band, count in sorted(bands["distribution"].items())
                    if band != "Needs Human Assessment"}
    routing_label_distribution: Dict[str, int] = {}
    for sample in samples:
        label = sample["human_routing_label"]
        routing_label_distribution[label] = routing_label_distribution.get(label, 0) + 1
    routing_label_distribution = dict(sorted(routing_label_distribution.items()))

    assistant_turns = [(str(s["id"]), str(t["id"])) for s in samples for t in s["turns"]
                       if t["speaker"] == "assistant"]
    prohibition = dict(pipe["prohibition_coverage"]())
    prohibition["corpus_assistant_turns"] = len(assistant_turns)
    prohibition["applicable_to_corpus_output"] = bool(assistant_turns)
    prohibition["note"] = ("The blind corpus contains no model output, so prohibition coverage is "
                           "measured against the validator's own lexicons, exactly as the red-team "
                           "report measures it. Author-written assistant turns are counted but are "
                           "not model output and are not scored as such.")

    sections: Dict[str, Any] = {
        "detector_metrics": {
            "per_detector": pipe["detector_table"](samples, preds),
            "excluded": dict(pipe["not_implemented"]),
            "denominator_note": "Every metric carries its denominator. A metric whose denominator is "
                                "zero is null, never 0.0 or 1.0.",
        },
        "by_language": {lang: _cut(pipe, samples, preds, subset)
                        for lang, subset in by_language.items()},
        "by_category": {name: _cut(pipe, samples, preds, subset)
                        for name, subset in categories.items()},
        "by_challenge_slice": {name: _cut(pipe, samples, preds, subset)
                               for name, subset in declared.items()},
        "label_slices": {name: _cut(pipe, samples, preds, subset)
                         for name, subset in label_slices.items()},
        "critical_misses": {
            "count": len(routing["critical_misses"]),
            "sample_ids": sorted(m["id"] for m in routing["critical_misses"]),
            "detail": [{k: v for k, v in m.items() if k != "tags"} for m in routing["critical_misses"]],
            "critical_event_miss_rate": routing["critical_event_miss_rate"],
            "critical_routing": routing["critical_routing"],
            "crisis_precheck": routing["crisis_precheck"],
            "crisis_precheck_misses": routing["crisis_precheck_misses"],
            "crisis_precheck_unexpected_fires": routing["crisis_precheck_unexpected_fires"],
        },
        "false_escalations": {
            "count": len(routing["false_escalations"]),
            "sample_ids": sorted(e["id"] for e in routing["false_escalations"]),
            "detail": [{k: v for k, v in e.items() if k != "tags"} for e in routing["false_escalations"]],
        },
        "abstention": dict(abstention),
        "evidence_link_validity": dict(evidence),
        "routing_labels": {
            "human_label_distribution": routing_label_distribution,
            "predicted_routed_critical": sum(1 for sid in preds if preds[sid]["routed_critical"]),
            "human_routed_critical": sum(1 for s in samples if s["expected"]["routed_critical"]),
            "critical_routing": routing["critical_routing"],
            "compared_as": "the human routing label thresholded at Critical, against the pipeline's "
                           "routed_critical. The pipeline emits no four-level routing, so no other "
                           "routing comparison is defined.",
            "band_substitution": "never: a routing label is not converted into an SVI band, and no "
                                 "band-accuracy metric is computed from one.",
        },
        "svi_distribution": {
            # Descriptive only. There is no human band label, so there is no
            # accuracy to compute; see band_ground_truth below.
            "scored_bands": scored_bands,
            "needs_human_assessment": needs_human,
            "not_scored_note": "Needs Human Assessment is an abstention, not a band. It is counted "
                               "separately and never appears among the scored bands.",
            "samples": len(samples),
            "band_ground_truth": {"available": BAND_GROUND_TRUTH_AVAILABLE,
                                  "reason": BAND_GROUND_TRUTH_REASON},
            "d4_structurally_unavailable": pipe["d4"](samples, preds),
            "svi_by_sample": {sid: preds[sid]["svi"] for sid in sorted(preds)},
        },
        "determinism": {
            "runs": determinism["runs"],
            "identical": determinism["identical"],
            "prediction_sha256": determinism["sha256"],
            "reported_predictions_match": reported_stable,
            "excluded_metadata": list(rs.NON_SUBSTANTIVE),
        },
        "scenario_replay": pipe["scenario_replay"](samples),
        "guardrail_prohibition_coverage": prohibition,
    }
    sections["abstention"]["needs_human_assessment"] = sections["svi_distribution"][
        "needs_human_assessment"]
    return {"sections": sections, "samples": samples, "predictions": preds}


def build_result(store: Store, pre: Mapping[str, Any], pipe: Mapping[str, Any],
                 measured: Mapping[str, Any], actor: Mapping[str, Any], run_id: str,
                 at: str, independent: bool) -> Dict[str, Any]:
    manifest = pre["manifest"]
    return {
        "result_version": rs.RESULT_VERSION,
        "run_id": run_id,
        "run_at": at,
        "run_by": {k: actor.get(k) for k in ("person_id", "identity", "role")},
        "independence": rs.INDEPENDENT if independent else rs.REGRESSION,
        "corpus": {
            "corpus_version": store.version,
            "plan_version": manifest.get("plan_version"),
            "corpus_sha256": manifest["corpus_sha256"],
            "freeze_manifest_sha256": freeze_manifest_sha256(store),
            "file_sha256": dict(manifest["file_sha256"]),
            "samples": len(measured["samples"]),
            "frozen_at": manifest.get("frozen_at"),
        },
        "ledger_heads": dict(manifest["ledger_heads"]),
        "versions": dict(pipe["versions"]),
        "derived_expectations": dict(DERIVED_EXPECTATIONS),
        "sections": measured["sections"],
    }


def freeze_manifest_sha256(store: Store) -> str:
    path = store.path("frozen", "freeze_manifest.json")
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- human-readable companion -------------------------------------------------------------


def render_markdown(result: Mapping[str, Any]) -> str:
    """A narrative-free summary. Sample and turn ids only, never scenario text."""
    sections = result["sections"]
    corpus = result["corpus"]
    lines: List[str] = [
        f"# Blind evaluation - corpus {corpus['corpus_version']}",
        "",
        f"**{result['independence']}** - run `{result['run_id']}` at {result['run_at']}",
        "",
        f"- samples: {corpus['samples']}",
        f"- corpus sha256: `{corpus['corpus_sha256']}`",
        f"- freeze manifest sha256: `{corpus['freeze_manifest_sha256']}`",
        f"- pipeline {result['versions']['pipeline_version']}, scoring "
        f"{result['versions']['scoring_version']}, lexicon {result['versions']['lexicon_version']}, "
        f"validator {result['versions']['validator_version']}",
        f"- deterministic across {sections['determinism']['runs']} runs: "
        f"{sections['determinism']['identical']}",
        "",
        "## Headline",
        "",
        f"- critical misses: {sections['critical_misses']['count']} "
        f"{sections['critical_misses']['sample_ids']}",
        f"- false escalations: {sections['false_escalations']['count']} "
        f"{sections['false_escalations']['sample_ids']}",
        f"- critical-event miss rate: "
        f"{sections['critical_misses']['critical_event_miss_rate']['miss_rate']}",
        f"- needs human assessment: {sections['svi_distribution']['needs_human_assessment']}",
        "",
        "## Detectors",
        "",
        "| detector | tp | fp | fn | precision | recall | f1 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in sorted(sections["detector_metrics"]["per_detector"].items()):
        if "excluded" in row:
            lines.append(f"| {name} | - | - | - | excluded | excluded | excluded |")
            continue
        lines.append(f"| {name} | {row['tp']} | {row['fp']} | {row['fn']} | {row['precision']} | "
                     f"{row['recall']} | {row['f1']} |")
    lines += ["", "## Languages", "", "| language | n | critical misses | false escalations |",
              "|---|---:|---:|---:|"]
    for lang, row in sorted(sections["by_language"].items()):
        routing = row.get("routing") or {}
        lines.append(f"| {lang} | {row['n']} | {len(routing.get('critical_misses') or [])} | "
                     f"{len(routing.get('false_escalations') or [])} |")
    lines += ["", "## Challenge slices", "", "| slice | n | critical misses | false escalations |",
              "|---|---:|---:|---:|"]
    for name, row in sorted(sections["by_challenge_slice"].items()):
        if not row["n"]:
            continue
        routing = row.get("routing") or {}
        lines.append(f"| {name} | {row['n']} | {len(routing.get('critical_misses') or [])} | "
                     f"{len(routing.get('false_escalations') or [])} |")
    lines += [
        "",
        "## Evidence and abstention",
        "",
        f"- cited-id validity: {sections['evidence_link_validity']['cited_validity']} "
        f"({sections['evidence_link_validity']['cited_ids']} ids)",
        f"- evidence exact agreement: {sections['evidence_link_validity']['evidence_exact_rate']} "
        f"({sections['evidence_link_validity']['true_positives_with_labels']} true positives with labels)",
        f"- abstention coverage: {sections['abstention']['abstention_coverage']} "
        f"({sections['abstention']['expected_abstain']} expected)",
        "",
        "## Routing labels (human) against routing behaviour (pipeline)",
        "",
        "".join(f"- human label {label}: {count}\n" for label, count in
                sections["routing_labels"]["human_label_distribution"].items()),
        f"- human routed Critical: {sections['routing_labels']['human_routed_critical']}",
        f"- pipeline routed Critical: {sections['routing_labels']['predicted_routed_critical']}",
        f"- {sections['routing_labels']['compared_as']}",
        "",
        "## SVI band distribution (descriptive)",
        "",
        "".join(f"- {band}: {count}\n" for band, count in
                sections["svi_distribution"]["scored_bands"].items()),
        f"- Needs Human Assessment (not a band): "
        f"{sections['svi_distribution']['needs_human_assessment']}",
        "",
        f"No band accuracy is reported: {sections['svi_distribution']['band_ground_truth']['reason']}",
        "",
        "## Derived expectations",
        "",
    ]
    for key, why in sorted(result["derived_expectations"].items()):
        lines.append(f"- `{key}`: {why}")
    lines += ["", "No scenario text appears in this report. Samples and turns are named by id only.", ""]
    return "\n".join(lines)


# --- steps 10-14 -------------------------------------------------------------------------


def run(store: Store, actor: Mapping[str, Any], regression: bool = False,
        at: Optional[str] = None) -> Dict[str, Any]:
    """The whole flow: preconditions, lazy import, measure, publish, expose."""
    at = at or now()
    pre = preflight(store, regression)                     # steps 3-8
    pipe = _pipeline()                                     # step 9
    run_id = run_id_for(pre["manifest"]["corpus_sha256"], at)
    independent = not regression

    rs.clean_temp(store)                                   # discard interrupted work
    measured = measure(store, pre, pipe)                   # steps 10-12
    if not measured["sections"]["determinism"]["reported_predictions_match"]:
        raise EvaluationError("the reported predictions do not match the stability check; nothing was "
                              "published and the corpus is unchanged", EXIT_EVALUATION_FAILED)
    if not measured["sections"]["determinism"]["identical"]:
        raise EvaluationError("the pipeline was not deterministic across repeat runs; nothing was "
                              "published and the corpus is unchanged", EXIT_EVALUATION_FAILED)
    result = build_result(store, pre, pipe, measured, actor, run_id, at, independent)

    if regression:
        comparison = rs.compare(pre["published"], result)
        result["compared_to"] = comparison
        published = rs.finalize(store, run_id, result, render_markdown(result), independent=False)
        return {"result": result, "paths": published, "comparison": comparison,
                "independence": result["independence"], "exposed": True}

    published = rs.finalize(store, run_id, result, render_markdown(result), independent=True)
    # Publication has happened. From here the corpus IS exposed; the records below
    # describe that fact and are repaired, never re-run, if they are interrupted.
    record_exposure_and_states(store, run_id, published["result_sha256"], actor, at,
                               [str(row["submission_id"]) for row in pre["corpus"]])
    return {"result": result, "paths": published, "comparison": None,
            "independence": result["independence"], "exposed": True}


def record_exposure_and_states(store: Store, run_id: str, result_hash: str, actor: Mapping[str, Any],
                               at: str, ids: Sequence[str]) -> Dict[str, Any]:
    """Write the exposure record and move every sample. Idempotent by design.

    Called after publication, and again by ``repair`` if it was interrupted. A
    sample already in ``contaminated_after_evaluation`` is skipped rather than
    re-transitioned, so re-running this never breaks the state ledger.
    """
    record = rs.record_exposure(store, run_id, result_hash, actor, at)
    moved = 0
    for sid in ids:
        state = store.state_of(sid)
        if state == "frozen":
            store.move(sid, "evaluated", actor, f"evaluated by run {run_id}",
                       {"result_sha256": result_hash}, at)
            state = "evaluated"
        if state == "evaluated":
            store.move(sid, "contaminated_after_evaluation", actor,
                       "the independent result for this corpus has been published",
                       {"result_sha256": result_hash}, at)
            moved += 1
    return {"exposure": record, "moved": moved}


def repair(store: Store, actor: Mapping[str, Any], at: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Recover the one non-atomic window: published result, missing exposure record."""
    if not rs.unrecorded_publication(store):
        return None
    published = rs.published_independent(store)
    corpus = store.read_frozen("corpus")
    return record_exposure_and_states(store, published.get("run_id", "unknown"),
                                      published.get("result_sha256", ""), actor, at or now(),
                                      [str(row["submission_id"]) for row in corpus])


# --- command line -------------------------------------------------------------------------


def _store_and_actor(args: argparse.Namespace) -> Tuple[Store, Dict[str, Any]]:
    """Steps 1-2: resolve the root and the version, and validate configuration."""
    check_version(args.version)
    store = Store.open(args.root, args.version)
    if args.actor:
        actor = store.actor(args.actor)
    else:
        actor = {"person_id": "", "identity": "", "role": ""}
    return store, actor


def cmd_run(args: argparse.Namespace) -> int:
    if not args.actor:
        raise EvaluationError("--actor is required for a run: an official evaluation must be "
                              "attributable to a named human on the roster", EXIT_USAGE)
    store, actor = _store_and_actor(args)
    repaired = repair(store, actor)
    if repaired is not None:
        print("recovered an interrupted run: the independent result was already published, so the "
              "exposure record and sample states were completed rather than re-evaluated")
        if not args.regression:
            return EXIT_OK
    outcome = run(store, actor, regression=args.regression)
    result = outcome["result"]
    if args.json:
        print(json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True))
    else:
        sections = result["sections"]
        print(f"{result['independence']}: {result['corpus']['samples']} sample(s), "
              f"{sections['critical_misses']['count']} critical miss(es), "
              f"{sections['false_escalations']['count']} false escalation(s), "
              f"deterministic {sections['determinism']['identical']}")
        print(f"result sha256 {outcome['paths']['result_sha256']}; written to "
              f"{outcome['paths']['json'].name} outside Git")
        if outcome["comparison"]:
            print(f"compared against the independent result: identical "
                  f"{outcome['comparison']['identical']}; changed sections "
                  f"{outcome['comparison']['changed_sections']}")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    store, _ = _store_and_actor(args)
    manifest = store.frozen_manifest()
    published = rs.published_independent(store)
    exposure = rs.exposure_record(store)
    payload = {
        "corpus_version": store.version,
        "frozen": manifest is not None,
        "samples": manifest["samples"] if manifest else 0,
        "independent_result_published": published is not None,
        "independent_run_id": (published or {}).get("run_id"),
        "independent_result_sha256": (published or {}).get("result_sha256"),
        "exposed": bool(exposure),
        "official_metrics_available": published is not None,
        "unrecorded_publication": rs.unrecorded_publication(store),
        "pending_temporary_artefacts": rs.pending_artefacts(store),
        "required_sections": list(rs.REQUIRED_SECTIONS),
    }
    if args.json:
        print(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True))
    elif manifest is None:
        print(f"no frozen corpus for {store.version}: locked count 0, official metrics unavailable, "
              "awaiting independent human authoring and review")
    else:
        print(f"frozen corpus {store.version}: {manifest['samples']} sample(s); independent result "
              f"published {payload['independent_result_published']}; exposed {payload['exposed']}")
    return EXIT_OK if manifest is not None else EXIT_NO_FROZEN_CORPUS


def cmd_clean_temp(args: argparse.Namespace) -> int:
    store, _ = _store_and_actor(args)
    removed = rs.clean_temp(store)
    print(f"removed {len(removed)} temporary run directory(ies); no finalized result was touched")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ml.eval.blind_evaluation",
        description="One-time official evaluation on a frozen blind corpus. It has no threshold, "
                    "weight or lexicon option: tuning through this command is impossible.")
    parser.add_argument("--root", default="", help=f"private evaluation root (default: ${ROOT_ENV})")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--actor", default="", help="roster person_id responsible for the run")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="evaluate a frozen corpus (refuses without one)")
    p.add_argument("--regression", action="store_true",
                   help="required for any run after the independent one; labels the result "
                        "regression_after_exposure and never overwrites the independent result")
    p.set_defaults(fn=cmd_run)
    sub.add_parser("status", help="whether an official evaluation exists").set_defaults(fn=cmd_status)
    sub.add_parser("clean-temp", help="remove temporary artefacts from interrupted runs"
                   ).set_defaults(fn=cmd_clean_temp)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except EvaluationError as exc:
        print(f"refused: {exc}")
        return exc.code
    except rs.ResultError as exc:
        print(f"refused: {exc}")
        return EXIT_EVALUATION_FAILED
    except LedgerError as exc:
        print(f"refused: {exc}")
        return EXIT_LEDGER
    except StateError as exc:
        print(f"refused: {exc}")
        return EXIT_STATE
    except StoreError as exc:
        print(f"refused: {exc}")
        return exc.code
    except RootError as exc:
        print(f"refused: {exc}")
        return EXIT_USAGE


if __name__ == "__main__":
    firewall.assert_clean("blind_evaluation")
    sys.exit(main())
