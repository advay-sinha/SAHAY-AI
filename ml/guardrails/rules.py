"""Deterministic output-rule engine. Standard library only, no I/O, no logging.

    check(text) -> {"category", "rule_id", "severity"} | None
    hits(text)  -> every matching rule, for tests and the evaluation

The result names the category and the rule id only. It never contains the
matched words, so a rejection reason cannot echo unsafe text back to anyone.
"""

import re
import unicodedata
from typing import Dict, List, Optional, Pattern, Tuple

from .lexicons.output_rules import CATEGORY_SEVERITY, RULES, RULES_VERSION
from .normalize import tokens

__all__ = ["check", "hits", "RULES_VERSION"]

_GAP = re.compile(r"~(\d+)")
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _prepare(pattern: str) -> Pattern[str]:
    """Fold the pattern like the text, expand ~N gaps, anchor on whole words."""
    folded = unicodedata.normalize("NFKC", pattern).casefold()
    folded = folded.replace("़", "").replace("ँ", "ं")
    # "a ~2 b": the gap owns its leading space, so "a b" (zero words) still matches.
    expanded = _GAP.sub(lambda m: r"(?: [^ |?]+){0," + m.group(1) + r"}", folded)
    expanded = expanded.replace(" (?: [^", "(?: [^")
    return re.compile(r"(?<= )(?:" + expanded + r")(?= )")


_COMPILED: List[Tuple[str, str, Pattern[str]]] = sorted(
    ((rid, cat, _prepare(p)) for rid, cat, _lang, p in RULES),
    key=lambda r: (_SEVERITY_ORDER[CATEGORY_SEVERITY[r[1]]], r[0]),
)


def hits(text: Optional[str]) -> List[Dict[str, str]]:
    if not text:
        return []
    t = tokens(text)
    return [{"category": cat, "rule_id": rid, "severity": CATEGORY_SEVERITY[cat]}
            for rid, cat, rx in _COMPILED if rx.search(t)]


def check(text: Optional[str]) -> Optional[Dict[str, str]]:
    """The first (most severe, then lowest id) matching rule, or None."""
    if not text:
        return None
    t = tokens(text)
    for rid, cat, rx in _COMPILED:
        if rx.search(t):
            return {"category": cat, "rule_id": rid, "severity": CATEGORY_SEVERITY[cat]}
    return None
