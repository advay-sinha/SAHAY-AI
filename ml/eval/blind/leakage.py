"""Deterministic leakage and similarity controls. Standard library only.

Independence is only real if a new submission is not one of the samples the
pipeline has already been tuned and reported on. This module builds an index
of every exposed text in the repository and compares a submission against it
with plain string and set operations. No fuzzy-matching library is used, and
none may be added: every rule here is readable and reproducible.

Exposed sources (all of them, by construction rather than by a hand-kept list)

  ml/eval/corpus/dev.json               development split, tuned on
  ml/eval/corpus/candidates.json        every outcome published
  ml/eval/corpus/redteam.json           every outcome published
  ml/eval/corpus/redteam_hardening.json written alongside the rules
  ml/eval/corpus/redteam_urgency.json   written alongside the rules

plus every fixture id named in ``ml.eval.contamination`` as a published
failure or a regression target, which is what makes "published failures remain
ineligible" checkable rather than aspirational.

Findings have two severities:

  block  the submission is, to a normalisation, one of the exposed samples.
         Exact text match, content-hash match, a reordered set of the same
         turns, a substantive turn reproduced verbatim, or a declared lineage
         whose parent is exposed. A human may not clear these: the sample can
         only be rejected or re-authored from scratch under a new id.
  warn   the submission is suspiciously close: high token overlap, or a shared
         distinctive phrase. These require human adjudication and a recorded
         reason. They are NOT rejections; two people writing about a police
         station will share vocabulary.

Common short safety phrases ("I need help", "muje madad chahiye",
"मुझे मदद चाहिई") are the words real callers use, and a corpus that
forbids them is not a corpus of real language. A turn whose whole text is one
of those phrases never raises a turn-level block on its own, and short turns
are excluded from the phrase and overlap rules entirely. What is caught is the
reproduction of a *scenario*.

Limits, stated
  * Cross-script copying (a Devanagari fixture transliterated to Latin by hand)
    is not detected by string comparison. It is covered by the author
    attestation, the declared-lineage rules and human review, not by this
    module.
  * A close paraphrase that shares no 6-token window and little vocabulary will
    pass. That is why authors must not have read the exposed corpora, which is
    a staffing rule, not a software one.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .. import contamination as ct
from . import normalize as nz
from .submission import content_sha256

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"

#: Every file whose text is exposed. locked.json is deliberately absent: it is
#: empty, and a future frozen corpus is compared through its own manifest.
EXPOSED_FILES = (
    "dev.json",
    "candidates.json",
    "redteam.json",
    "redteam_hardening.json",
    "redteam_urgency.json",
)

#: Tuning knobs. Deliberately blunt and deliberately visible.
OVERLAP_WARN = 0.70          # Jaccard token overlap that earns a warning
MIN_OVERLAP_TOKENS = 8       # shorter texts are too small for overlap to mean anything
SHINGLE_N = 6                # window length for a "distinctive phrase"
MIN_TURN_TOKENS_FOR_BLOCK = 5  # a turn shorter than this cannot block on its own

#: Phrases that are common property. Matched on the WHOLE normalised turn only.
COMMON_SAFE_PHRASES = frozenset({
    nz.compare(p) for p in (
        "i need help", "i need some help", "please help me", "help me", "can you help me",
        "i want to talk to someone", "i need to talk to a person", "hello", "are you there",
        "what should i do", "i do not know what to do", "thank you", "yes", "no", "ok",
        "mujhe madad chahiye", "muje madad chahiye", "mujhe help chahiye", "madad kijiye",
        "kya karna chahiye", "koi hai", "please help",
        "मुझे मदद चाहिए", "मदद कीजिए", "कोई है", "मैं क्या करूं",
        "क्या करना चाहिए", "नमस्ते", "धन्यवाद", "हां", "नहीं",
    )
})


class LeakageError(Exception):
    """The exposed index could not be built."""


# --- the exposed index ----------------------------------------------------------------


def _victim_texts(item: Mapping[str, Any]) -> List[str]:
    """Victim-side text of one exposed item, whichever corpus shape it uses."""
    if "turns" in item:
        return [str(t.get("text", "")) for t in item["turns"] if t.get("speaker") == "victim"]
    if "text" in item:  # red-team cases are a single victim utterance
        return [str(item["text"])]
    return []


def _items(corpus: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    return corpus.get("samples") or corpus.get("cases") or ()


def build_index(corpus_dir: Path = CORPUS_DIR, files: Iterable[str] = EXPOSED_FILES) -> Dict[str, Any]:
    """Index every exposed text. Read-only: no corpus file is ever written."""
    by_scenario: Dict[str, str] = {}      # normalised whole-scenario text -> sample id
    by_turn: Dict[str, List[str]] = {}    # normalised turn text -> sample ids
    by_turnset: Dict[Tuple[str, ...], str] = {}  # sorted tuple of turns -> sample id
    tokens: Dict[str, Set[str]] = {}      # sample id -> token set
    shingle_owners: Dict[Tuple[str, ...], Set[str]] = {}
    ids: List[str] = []
    for name in files:
        path = Path(corpus_dir) / name
        if not path.is_file():
            raise LeakageError(f"exposed corpus file {name} is missing; the leakage index cannot be trusted")
        try:
            corpus = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise LeakageError(f"exposed corpus file {name} is not valid JSON: {exc}") from None
        for item in _items(corpus):
            sid = str(item.get("id", ""))
            ids.append(sid)
            texts = [t for t in _victim_texts(item) if t.strip()]
            scenario = nz.compare(" ".join(texts))
            if scenario:
                by_scenario.setdefault(scenario, sid)
                tokens[sid] = nz.token_set(scenario)
                for sh in nz.shingles(scenario, SHINGLE_N):
                    shingle_owners.setdefault(sh, set()).add(sid)
            norm_turns = []
            for text in texts:
                key = nz.compare(text)
                if not key:
                    continue
                norm_turns.append(key)
                by_turn.setdefault(key, []).append(sid)
            if norm_turns:
                by_turnset.setdefault(tuple(sorted(norm_turns)), sid)
    return {
        "files": tuple(files),
        "ids": tuple(ids),
        "scenarios": by_scenario,
        "turns": by_turn,
        "turnsets": by_turnset,
        "tokens": tokens,
        "shingles": shingle_owners,
        "content_hashes": exposed_content_hashes(corpus_dir, files),
    }


def exposed_content_hashes(corpus_dir: Path = CORPUS_DIR,
                           files: Iterable[str] = EXPOSED_FILES) -> Dict[str, str]:
    """``content_sha256``-shaped hash of every exposed item's turn text.

    The hash is taken over the same normalised victim text a submission would
    produce, so an identical scenario collides even when ids and metadata
    differ. It is a stable content hash, not the submission hash itself.
    """
    out: Dict[str, str] = {}
    import hashlib
    for name in files:
        path = Path(corpus_dir) / name
        if not path.is_file():
            continue
        corpus = json.loads(path.read_text(encoding="utf-8"))
        for item in _items(corpus):
            texts = [nz.compare(t) for t in _victim_texts(item) if t.strip()]
            if not texts:
                continue
            digest = hashlib.sha256(json.dumps(texts, ensure_ascii=False,
                                               separators=(",", ":")).encode("utf-8")).hexdigest()
            out[digest] = str(item.get("id", ""))
    return out


def exposed_ids(index: Optional[Mapping[str, Any]] = None) -> Set[str]:
    """Every id that cannot be independent evidence: the exposed corpora plus
    every fixture named as a published failure or a regression target."""
    known = set(ct.CANDIDATE_KNOWN_FAILURES) | set(ct.DEV_KNOWN_FAILURES) \
        | set(ct.REDTEAM_KNOWN_FAILURES) | set(ct.REGRESSION_TARGETS_HARDENING)
    if index is not None:
        known |= set(index["ids"])
    return known


# --- checking a submission ------------------------------------------------------------


def _submission_content_hash(submission: Mapping[str, Any]) -> str:
    import hashlib
    texts = [nz.compare(str(t.get("text", ""))) for t in submission.get("turns") or []
             if t.get("speaker") == "victim" and str(t.get("text", "")).strip()]
    return hashlib.sha256(json.dumps(texts, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def check(submission: Mapping[str, Any], index: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Leakage findings for one submission, most severe first.

    A finding is ``{"check", "severity", "matched_id", "turn", "detail"}``.
    ``detail`` is a number or a class name; it never contains scenario text.
    """
    findings: List[Dict[str, Any]] = []
    turns = [t for t in (submission.get("turns") or []) if isinstance(t, Mapping)]
    victim = [str(t.get("text", "")) for t in turns if t.get("speaker") == "victim"]
    scenario = nz.compare(" ".join(v for v in victim if v.strip()))

    def add(name: str, severity: str, matched: str, turn: Optional[str] = None, detail: Any = None) -> None:
        findings.append({"check": name, "severity": severity, "matched_id": matched,
                         "turn": turn, "detail": detail})

    # 1. the whole scenario, normalised, is an exposed sample
    if scenario and scenario in index["scenarios"]:
        add("exact_normalized_match", "block", index["scenarios"][scenario])

    # 2. stable content-hash match (same normalised victim turns, any metadata)
    digest = _submission_content_hash(submission)
    if digest in index["content_hashes"]:
        add("content_hash_match", "block", index["content_hashes"][digest], detail="sha256")

    # 3. the same turns in a different order
    norm_turns = [nz.compare(v) for v in victim if nz.compare(v)]
    if norm_turns:
        key = tuple(sorted(norm_turns))
        owner = index["turnsets"].get(key)
        if owner and scenario not in index["scenarios"]:
            add("reordered_turn_match", "block", owner, detail="same turn set, different order")

    # 4. a substantive turn reproduced verbatim (common phrases excluded)
    for t in turns:
        if t.get("speaker") != "victim":
            continue
        norm = nz.compare(str(t.get("text", "")))
        if not norm or norm in COMMON_SAFE_PHRASES:
            continue
        if len(nz.token_list(norm)) < MIN_TURN_TOKENS_FOR_BLOCK:
            continue
        owners = index["turns"].get(norm)
        if owners:
            add("turn_level_match", "block", sorted(set(owners))[0], turn=str(t.get("id")),
                detail=f"{len(set(owners))} exposed sample(s)")

    # 5. declared lineage from an exposed sample
    lineage = submission.get("lineage")
    if isinstance(lineage, Mapping) and lineage.get("parent_id"):
        parent = str(lineage["parent_id"])
        if parent in exposed_ids(index):
            add("declared_derivation_from_exposed", "block", parent,
                detail=str(lineage.get("relation", "derived")))

    # 6. high token overlap (warning only)
    sub_tokens = nz.token_set(scenario)
    if len(sub_tokens) >= MIN_OVERLAP_TOKENS:
        best: Tuple[float, str] = (0.0, "")
        for sid, toks in index["tokens"].items():
            if len(toks) < MIN_OVERLAP_TOKENS:
                continue
            union = len(sub_tokens | toks)
            score = len(sub_tokens & toks) / union if union else 0.0
            if score > best[0]:
                best = (score, sid)
        if best[0] >= OVERLAP_WARN:
            add("high_token_overlap", "warn", best[1], detail=round(best[0], 3))

    # 7. a shared distinctive phrase (warning only): a 6-token window that
    #    exactly one exposed sample uses
    for sh in sorted(nz.shingles(scenario, SHINGLE_N)):
        owners = index["shingles"].get(sh)
        if owners and len(owners) == 1:
            add("shared_distinctive_phrase", "warn", sorted(owners)[0],
                detail=f"{SHINGLE_N}-token window")
            break

    order = {"block": 0, "warn": 1}
    return sorted(findings, key=lambda f: (order[f["severity"]], f["check"], str(f["matched_id"])))


def worst(findings: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """"block", "warn" or None."""
    if any(f["severity"] == "block" for f in findings):
        return "block"
    if findings:
        return "warn"
    return None


def declared_lineage_chain(submission: Mapping[str, Any],
                           submissions: Mapping[str, Mapping[str, Any]]) -> List[str]:
    """Declared ancestry of a submission, nearest parent first.

    Follows ``lineage.parent_id`` through the private submission set. A cycle
    stops the walk rather than looping. Used by the freeze gate: if any
    ancestor is exposed, the descendant is not independent evidence either.
    """
    chain: List[str] = []
    seen: Set[str] = set()
    lineage = submission.get("lineage")
    current = str(lineage["parent_id"]) if isinstance(lineage, Mapping) and lineage.get("parent_id") else ""
    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        parent = submissions.get(current, {}).get("lineage")
        current = str(parent["parent_id"]) if isinstance(parent, Mapping) and parent.get("parent_id") else ""
    return chain


def submission_hash_matches(submission: Mapping[str, Any]) -> bool:
    """Convenience for the freeze gate: the declared content hash still holds."""
    try:
        return str(submission.get("content_sha256")) == content_sha256(submission)
    except Exception:
        return False
