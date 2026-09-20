"""The versioned coverage plan and coverage accounting. Standard library only.

The plan (``coverage_plan_<version>.json``) states how many independently
authored samples each language, category and challenge slice needs, and why.
It is a target for human authors. Nothing in this module writes a sample,
guesses a label or relaxes a minimum: it counts what humans produced and
reports the shortfall that blocks a freeze.

Category membership comes from the *frozen human labels*, not from the
author's intention, with four derived buckets:

  low_distress_information_request  no detector label positive and the routing
                                    label is Low
  expected_abstention               the reviewers expect needs_human, no score
  no_alert_control                  no detector label positive and routing is
                                    not Critical
  multi_label                       two or more detector labels positive

Slice membership is author-declared structural metadata (``intended_slices``).
A reviewer may flag a slice as wrong, which removes it from the count; nothing
else infers a slice. That is deliberate: a slice is bookkeeping, not evidence,
and inferring it with a heuristic would put a prediction inside the corpus
tooling.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from ..schema import DETECTOR_CATEGORIES
from .paths import check_version

PLAN_DIR = Path(__file__).resolve().parent
PLAN_SCHEMA = "sahay-blind-coverage-plan"

#: Buckets computed from labels rather than named by a detector.
DERIVED_CATEGORIES = (
    "low_distress_information_request",
    "expected_abstention",
    "no_alert_control",
    "multi_label",
)
CATEGORY_NAMES = tuple(DETECTOR_CATEGORIES) + DERIVED_CATEGORIES

#: Every challenge slice an author may declare. Frozen with the plan version.
SLICE_NAMES = (
    "explicit_negation",
    "clause_scoped_negation",
    "conditional_language",
    "quoted_speech",
    "attributed_speech",
    "danger_plus_attributed_language",
    "past_tense_disclosure",
    "indirect_language",
    "code_switching",
    "romanised_hindi",
    "misspellings",
    "regional_vocabulary",
    "polite_understated_danger",
    "multiple_weak_dimensions",
    "conflicting_reassurance",
    "adversarial_roleplay",
    "prompt_injection",
    "embedded_instructions",
    "multi_turn_evidence",
    "later_turn_evidence",
    "repeated_or_corrected_information",
    "safe_near_miss",
)

LANGUAGES = ("en", "hi", "hinglish")
SCRIPTS = ("latin", "devanagari", "mixed")


class PlanError(Exception):
    """The plan file is missing, malformed or inconsistent."""


def plan_path(version: str) -> Path:
    return PLAN_DIR / f"coverage_plan_{check_version(version)}.json"


def load_plan(version: str = "v1", path: Path = None) -> Dict[str, Any]:
    p = Path(path) if path is not None else plan_path(version)
    if not p.is_file():
        raise PlanError(f"no coverage plan for corpus version {version!r}")
    try:
        plan = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise PlanError(f"coverage plan is not valid JSON: {exc}") from None
    errs = validate_plan(plan)
    if errs:
        raise PlanError("; ".join(errs))
    return plan


def validate_plan(plan: Mapping[str, Any]) -> List[str]:
    """Structural problems with a plan. Empty means usable."""
    errs: List[str] = []
    required = ("schema", "plan_version", "corpus_version", "description", "total_min",
                "no_stereotype_rule", "languages", "categories", "slices", "notes")
    for key in required:
        if key not in plan:
            errs.append(f"plan: missing {key}")
    if errs:
        return errs
    if plan["schema"] != PLAN_SCHEMA:
        errs.append(f"plan: schema must be {PLAN_SCHEMA}")
    if not isinstance(plan["total_min"], int) or plan["total_min"] < 1:
        errs.append("plan: total_min must be a positive integer")

    langs = plan["languages"]
    seen_lang = set()
    for entry in langs:
        name = entry.get("language")
        if name not in LANGUAGES:
            errs.append(f"plan: unknown language {name!r}")
        if name in seen_lang:
            errs.append(f"plan: duplicate language {name!r}")
        seen_lang.add(name)
        for s in entry.get("script") or []:
            if s not in SCRIPTS:
                errs.append(f"plan: unknown script {s!r}")
        if not isinstance(entry.get("min"), int) or entry["min"] < 0:
            errs.append(f"plan: language {name!r} needs an integer min")
        if not str(entry.get("why", "")).strip():
            errs.append(f"plan: language {name!r} needs a why")
    if seen_lang != set(LANGUAGES):
        errs.append(f"plan: every language in {LANGUAGES} needs a target")
    if sum(e.get("min", 0) for e in langs) < plan["total_min"]:
        errs.append("plan: language minimums do not reach total_min")

    for kind, key, allowed in (("category", "categories", CATEGORY_NAMES), ("slice", "slices", SLICE_NAMES)):
        seen = set()
        for entry in plan[key]:
            name = entry.get(kind)
            if name not in allowed:
                errs.append(f"plan: unknown {kind} {name!r}")
            if name in seen:
                errs.append(f"plan: duplicate {kind} {name!r}")
            seen.add(name)
            if not isinstance(entry.get("min_total"), int) or entry["min_total"] < 0:
                errs.append(f"plan: {kind} {name!r} needs an integer min_total")
            if not isinstance(entry.get("min_per_language"), int) or entry["min_per_language"] < 0:
                errs.append(f"plan: {kind} {name!r} needs an integer min_per_language")
            for lang in entry.get("languages", []):
                if lang not in LANGUAGES:
                    errs.append(f"plan: {kind} {name!r} names unknown language {lang!r}")
            if not str(entry.get("why", "")).strip():
                errs.append(f"plan: {kind} {name!r} needs a why")
        missing = set(allowed) - seen
        if missing:
            errs.append(f"plan: no target for {kind}(s) {sorted(missing)}")
    return errs


# --- accounting -----------------------------------------------------------------------


def categories_of(labels: Mapping[str, bool], routing: str, abstain: bool) -> List[str]:
    """The plan categories one frozen label set belongs to."""
    positives = [c for c in DETECTOR_CATEGORIES if bool(labels.get(c))]
    out = list(positives)
    if not positives and routing == "Low":
        out.append("low_distress_information_request")
    if abstain:
        out.append("expected_abstention")
    if not positives and routing != "Critical":
        out.append("no_alert_control")
    if len(positives) >= 2:
        out.append("multi_label")
    return out


def _entry_languages(entry: Mapping[str, Any]) -> Sequence[str]:
    named = entry.get("languages")
    return tuple(named) if named else LANGUAGES


def coverage(plan: Mapping[str, Any], items: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Count coverage for ``items`` and list every shortfall.

    Each item is ``{"language": ..., "categories": [...], "slices": [...]}``.
    No narrative is read, so this report is safe to write inside Git.
    """
    items = list(items)
    by_lang: Dict[str, int] = {lang: 0 for lang in LANGUAGES}
    cat_total: Dict[str, int] = {c: 0 for c in CATEGORY_NAMES}
    cat_lang: Dict[str, Dict[str, int]] = {c: dict.fromkeys(LANGUAGES, 0) for c in CATEGORY_NAMES}
    slice_total: Dict[str, int] = {s: 0 for s in SLICE_NAMES}
    slice_lang: Dict[str, Dict[str, int]] = {s: dict.fromkeys(LANGUAGES, 0) for s in SLICE_NAMES}

    for item in items:
        lang = item.get("language")
        if lang in by_lang:
            by_lang[lang] += 1
        for c in item.get("categories") or []:
            if c in cat_total:
                cat_total[c] += 1
                if lang in cat_lang[c]:
                    cat_lang[c][lang] += 1
        for s in set(item.get("slices") or []):
            if s in slice_total:
                slice_total[s] += 1
                if lang in slice_lang[s]:
                    slice_lang[s][lang] += 1

    shortfalls: List[Dict[str, Any]] = []
    if len(items) < plan["total_min"]:
        shortfalls.append({"kind": "total", "name": "total", "language": None,
                           "have": len(items), "need": plan["total_min"]})
    for entry in plan["languages"]:
        lang = entry["language"]
        if by_lang[lang] < entry["min"]:
            shortfalls.append({"kind": "language", "name": lang, "language": lang,
                               "have": by_lang[lang], "need": entry["min"]})
    for kind, key, totals, per_lang in (("category", "categories", cat_total, cat_lang),
                                        ("slice", "slices", slice_total, slice_lang)):
        for entry in plan[key]:
            name = entry[kind]
            if totals[name] < entry["min_total"]:
                shortfalls.append({"kind": kind, "name": name, "language": None,
                                   "have": totals[name], "need": entry["min_total"]})
            for lang in _entry_languages(entry):
                if per_lang[name][lang] < entry["min_per_language"]:
                    shortfalls.append({"kind": kind, "name": name, "language": lang,
                                       "have": per_lang[name][lang], "need": entry["min_per_language"]})
    return {
        "plan_version": plan["plan_version"],
        "corpus_version": plan["corpus_version"],
        "samples": len(items),
        "total_min": plan["total_min"],
        "by_language": by_lang,
        "by_category": {c: {"total": cat_total[c], "by_language": cat_lang[c]} for c in CATEGORY_NAMES},
        "by_slice": {s: {"total": slice_total[s], "by_language": slice_lang[s]} for s in SLICE_NAMES},
        "shortfalls": shortfalls,
        "satisfied": not shortfalls,
    }
