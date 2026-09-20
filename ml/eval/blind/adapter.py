"""Adapter: frozen blind-corpus schema -> the existing evaluator's sample shape.

Standard library only, and no prediction module in the import graph: this is
dict shaping, so it is safe to import before a freeze is verified.

The two schemas exist for different reasons and neither should be bent to the
other. The private schema separates the narrative (`corpus.json`) from the
human labels (`labels.json`) because a reviewer must never see a label, and it
carries a routing label rather than the evaluator's `expected` block because
reviewers annotate what should happen, not pipeline internals. `ml/eval/evaluate.py`
wants one merged sample of the shape `ml/eval/schema.py` defines. This module
is the single, explicit place where one becomes the other.

Every derivation is listed here rather than buried in a comprehension:

  id                 the private `submission_id`, kept verbatim. It stays in
                     the `SUB-` namespace deliberately: a blind sample must
                     never be mistakable for a `DEV-`, `CAND-` or `LOCK-`
                     fixture, which is also why `schema.validate_sample` is
                     not applied to the result (it would demand one of those
                     prefixes). `validate_adapted` checks every other field
                     the evaluator actually reads.
  channel            fixed to `mobile_chat`. The blind corpus is written text
                     with no audio, so the acoustic dimension D4 is
                     structurally unavailable for every sample. This is a
                     stated limitation of the corpus, not a modelling choice:
                     no acoustic claim can be made from these results.
  labels             the frozen human labels, unchanged.
  expected_evidence  the frozen human evidence turns, unchanged.
  human_routing_label  the reviewers' routing label, carried verbatim and
                     compared only against the pipeline's routing behaviour.
  expected.routed_critical   the routing label thresholded at `Critical`. This
                     is the routing label itself, not a band.
  expected.abstain   the reviewers' `expected_abstention`.
  expected.band      ALWAYS `None`. See below.
  expected.crisis_precheck   a DERIVED PROXY from the reviewed
                     `crisis_self_harm` label, not a separately annotated
                     ground truth. Reviewers are blind to pipeline internals
                     and are never asked whether a synchronous pre-check should
                     fire, so this restates the schema's own rule that a
                     crisis-positive sample must expect the pre-check. It is
                     recorded in every report under `derived_expectations`.
  tags               empty. `schema.TAGS` and the blind challenge slices are
                     different vocabularies; the declared slices travel in
                     `declared_slices` and are cut separately, so no schema tag
                     is ever asserted that a human did not choose.

Routing label and SVI band are not the same thing
-------------------------------------------------
They share the vocabulary `Low | Moderate | High | Critical` and nothing else:

  routing label   what a human says should HAPPEN — who is woken up and how
                  fast. It is annotated by two blind reviewers.
  SVI band        what the deterministic scorer OUTPUTS for a conversation. It
                  is a pipeline artefact, not a human judgement.
  Needs Human     the abstention representation: no score was produced at all.
  Assessment      It is not a band and is never counted as one.

An earlier version of this adapter set `expected.band` to the routing label
because the two enumerations look alike. That was wrong: it would have let the
report publish a "band accuracy" computed against a label no human ever gave,
and a system could have scored well on it by agreeing with a translation of a
different question. `expected.band` is therefore `None` for every blind sample,
which is how `ml/eval/evaluate.py` already represents unspecified ground truth —
no value is fabricated to satisfy the old API — and the blind report reports the
band distribution descriptively and emits no band-accuracy metric at all.

`declared_slices` is an extra key the evaluator ignores. It is author-declared
metadata used only to cut metrics, never evidence.
"""

from typing import Any, Dict, List, Mapping, Sequence

from ..schema import BANDS, CATEGORIES, CHANNELS, DETECTOR_CATEGORIES, LANGUAGES, SPEAKERS
from .plan import SLICE_NAMES

ADAPTER_VERSION = "1.1.0"

#: Channels on which acoustic distress (D4) has no measurement path by design.
#: Mirrors `text_channel` in the frozen enum block of docs/contracts/CONTRACTS.md
#: section 9 (PC-10) and `backend/app/core/enums.py::TEXT_CHANNELS`. It is
#: restated rather than imported because importing `ml.assessment` would breach
#: the prediction firewall; `ml/tests/test_blind_evaluation.py` parses the
#: frozen contract block and fails if this copy drifts.
TEXT_CHANNELS = ("mobile_chat", "portal_chat")

#: Every blind sample is written text. Audio is out of scope for this corpus.
#: `mobile_chat` is canonical: it is listed in both `session_channel` and
#: `text_channel` in the frozen enum block.
CHANNEL = "mobile_chat"

#: The blind annotation schema does not ask anyone to label an SVI band, so
#: there is no band ground truth and no band-accuracy metric may be computed.
BAND_GROUND_TRUTH_AVAILABLE = False
BAND_GROUND_TRUTH_REASON = (
    "the blind annotation schema asks reviewers for a routing label (what should happen), never for "
    "an SVI band (what the scorer outputs). No human band label exists, so the band distribution is "
    "reported descriptively and no band-accuracy metric is computed.")

#: Derivations a reader of the report must be told about.
DERIVED_EXPECTATIONS = {
    "channel": f"fixed to {CHANNEL!r}, a canonical text channel (frozen enum block, "
               "docs/contracts/CONTRACTS.md section 9): the corpus is written text, so D4 "
               "(acoustics) is structurally unavailable for every sample and no acoustic claim "
               "can be made from these results",
    "expected.crisis_precheck": "a DERIVED PROXY from the reviewed crisis_self_harm label, not a "
                                "separately annotated ground truth; reviewers are blind to pipeline "
                                "internals and never annotate the pre-check",
    "expected.routed_critical": "the human routing label thresholded at Critical; it is the routing "
                                "label, not a band",
    "expected.band": "always null: no human band label exists. " + BAND_GROUND_TRUTH_REASON,
    "tags": "empty: the schema tag vocabulary is not the blind challenge-slice vocabulary",
}


class AdapterError(Exception):
    """A frozen corpus and its labels cannot be merged into evaluator samples."""


def adapt(scenario: Mapping[str, Any], labels: Mapping[str, Any]) -> Dict[str, Any]:
    """Merge one frozen scenario and its frozen labels into an evaluator sample."""
    if str(scenario.get("submission_id")) != str(labels.get("submission_id")):
        raise AdapterError("scenario and label rows do not name the same submission")
    routing = labels.get("routing")
    if routing not in BANDS:
        raise AdapterError(f"{scenario.get('submission_id')}: routing label {routing!r} is not one of "
                           f"{tuple(BANDS)}")
    label_map = dict(labels.get("labels") or {})
    return {
        "id": str(scenario["submission_id"]),
        "schema_version": None,           # the blind corpus carries its own versioning
        "split": "blind",
        "language": scenario["language"],
        "channel": CHANNEL,
        "tags": [],
        "turns": [dict(t) for t in scenario["turns"]],
        "labels": label_map,
        "expected_evidence": {k: list(v) for k, v in (labels.get("expected_evidence") or {}).items()},
        "expected": {
            "crisis_precheck": bool(label_map.get("crisis_self_harm")),
            "routed_critical": routing == "Critical",
            "abstain": bool(labels.get("expected_abstention")),
            # No human labelled an SVI band, so there is no band ground truth.
            # `None` is how ml/eval/evaluate.py represents "not specified"; it is
            # not a placeholder for a value that exists somewhere else.
            "band": None,
        },
        # The routing label travels under its own name so that no code path can
        # read it as a band by accident.
        "human_routing_label": routing,
        "review": {"status": "blind_frozen", "required_reviews": None, "reviewers": []},
        "notes": "",
        "declared_slices": list(labels.get("declared_slices") or []),
    }


def adapt_all(corpus: Sequence[Mapping[str, Any]],
              labels: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Merge a whole frozen corpus. Refuses any mismatch between the two files."""
    by_id = {str(row.get("submission_id")): row for row in labels}
    if len(by_id) != len(labels):
        raise AdapterError("labels.json contains a duplicate submission id")
    if len(corpus) != len(labels):
        raise AdapterError(f"corpus has {len(corpus)} scenario(s) and labels has {len(labels)}")
    out: List[Dict[str, Any]] = []
    for scenario in corpus:
        sid = str(scenario.get("submission_id"))
        if sid not in by_id:
            raise AdapterError(f"{sid}: no frozen label row")
        out.append(adapt(scenario, by_id[sid]))
    return out


def validate_adapted(sample: Mapping[str, Any]) -> List[str]:
    """Every field the evaluator reads. Messages name ids, never narrative."""
    errs: List[str] = []
    sid = str(sample.get("id", "<no id>"))

    def err(message: str) -> None:
        errs.append(f"{sid}: {message}")

    if not sid or sid == "<no id>":
        return ["adapted sample has no id"]
    if sample.get("language") not in LANGUAGES:
        err(f"language {sample.get('language')!r}")

    channel = sample.get("channel")
    if channel not in CHANNELS:
        err(f"channel {channel!r} is not a canonical session_channel")
    elif channel not in TEXT_CHANNELS:
        err(f"channel {channel!r} is not a text channel; a written corpus must use one of "
            f"{TEXT_CHANNELS} so that D4 stays structurally unavailable")
    elif channel != CHANNEL:
        err(f"the blind corpus is adapted on {CHANNEL!r}")

    if sample.get("tags") != []:
        err("tags must be empty")

    routing = sample.get("human_routing_label")
    if routing not in BANDS:
        err(f"human_routing_label {routing!r} is not one of {tuple(BANDS)}")

    turns = sample.get("turns")
    victim_ids: set = set()
    if not isinstance(turns, list) or not turns:
        err("turns must be a non-empty list")
    else:
        seen = set()
        for t in turns:
            if not isinstance(t, Mapping) or not {"id", "speaker", "text", "state"} <= set(t):
                err("each turn needs id, speaker, text, state")
                continue
            if t["speaker"] not in SPEAKERS:
                err(f"turn {t['id']}: speaker {t['speaker']!r}")
            if not str(t["text"]).strip():
                err(f"turn {t['id']}: empty text")
            if str(t["id"]) in seen:
                err(f"duplicate turn id {t['id']}")
            seen.add(str(t["id"]))
            if t["speaker"] == "victim":
                victim_ids.add(str(t["id"]))
        if not victim_ids:
            err("at least one victim turn is required")

    labels = sample.get("labels")
    if not isinstance(labels, Mapping) or set(labels) != set(CATEGORIES):
        err(f"labels must have exactly the {len(CATEGORIES)} schema categories")
        labels = {}
    else:
        for name, value in labels.items():
            if not isinstance(value, bool):
                err(f"label {name} must be a bool")

    evidence = sample.get("expected_evidence")
    if not isinstance(evidence, Mapping):
        err("expected_evidence must be an object")
    else:
        for cat, ids in evidence.items():
            if cat not in DETECTOR_CATEGORIES:
                err(f"expected_evidence names non-detector category {cat!r}")
                continue
            if not labels.get(cat):
                err(f"expected_evidence for {cat} but the label is false")
            for i in ids or []:
                if str(i) not in victim_ids:
                    err(f"expected_evidence id {i!r} for {cat} is not a victim turn")
        for cat in DETECTOR_CATEGORIES:
            if labels.get(cat) and not (evidence.get(cat) or []):
                err(f"positive label {cat} has no expected_evidence")

    expected = sample.get("expected")
    if not isinstance(expected, Mapping) or set(expected) != {"crisis_precheck", "routed_critical",
                                                              "abstain", "band"}:
        err("expected must have exactly crisis_precheck, routed_critical, abstain, band")
    else:
        for key in ("crisis_precheck", "routed_critical", "abstain"):
            if not isinstance(expected[key], bool):
                err(f"expected.{key} must be a bool")
        # No human labels an SVI band, so a band here can only be a routing
        # label wearing a disguise. Refuse it outright rather than letting a
        # band-accuracy number be computed against a different question.
        if expected["band"] is not None:
            err("expected.band must be null: the blind annotation schema has no band label, and a "
                "routing label must never be substituted for one")
        if expected["band"] == routing and routing is not None:
            err("expected.band was taken from the routing label; routing and band are different "
                "concepts and cannot be substituted")
        if labels.get("crisis_self_harm") and not expected["crisis_precheck"]:
            err("a crisis-positive sample must expect the pre-check to fire")
        if (labels.get("crisis_self_harm") or labels.get("immediate_danger")) \
                and not expected["routed_critical"]:
            err("a critical label must expect routed_critical")
        if expected["routed_critical"] != (routing == "Critical"):
            err("expected.routed_critical does not match the human routing label")

    for name in sample.get("declared_slices") or []:
        if name not in SLICE_NAMES:
            err(f"unknown declared slice {name!r}")
    return errs


def validate_all(samples: Sequence[Mapping[str, Any]]) -> List[str]:
    errs: List[str] = []
    seen = set()
    for sample in samples:
        errs.extend(validate_adapted(sample))
        sid = str(sample.get("id"))
        if sid in seen:
            errs.append(f"{sid}: duplicate sample id in the adapted corpus")
        seen.add(sid)
    return errs
