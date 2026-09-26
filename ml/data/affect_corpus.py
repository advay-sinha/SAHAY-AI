"""Text-affect corpus for the MuRIL / XLM-R shadow branch (plan M12e, run R5; D-9a, EXT-123/125/129).

    python -m ml.data.affect_corpus fetch-goemotions     # network: 4 files from google-research (optional)
    python -m ml.data.affect_corpus build                # no network

Builds ``<SAHAY_TRAINING_ROOT>/textaffect/corpus-v1/{examples.jsonl, manifest.json}`` with one
row per utterance labelled ``affect:neutral|happy|sad|angry|fearful``:

* **EmoInHindi** (hi, Devanagari): per-turn labels from the privacy-processed normalised
  records. Mapping: anger -> angry; fear, apprehensive -> fearful; sad -> sad; joy -> happy;
  neutral -> neutral. Every other source emotion is ignored. A turn with several mapped
  classes takes the one with the highest source intensity; a tie is dropped, never folded.
* **Hinglish copy** (hinglish, Latin): each EmoInHindi turn romanised by
  ``ml.nlp.transliterate`` (a heuristic, marked ``derivation: transliterated``). It keeps the
  label and the split of its source dialogue, so no text crosses splits.
* **GoEmotions** (en; optional): single-label examples only. anger -> angry; fear,
  nervousness -> fearful; sadness -> sad; joy -> happy; neutral -> neutral.

Splits are **sentence-disjoint**. EmoInHindi dialogues reuse template lines: v1 split by
dialogue, and 84% of its test sentences also appeared verbatim in training, so its scores
measured memorisation. v2 collapses exact duplicates (after whitespace and punctuation
normalisation) into one row with a majority label (at least 2/3 agreement, otherwise dropped),
and groups near-duplicates (word-set Jaccard >= 0.8) so that each group shares one split,
assigned from a seeded hash of the group's representative text (70/15/15). A final pass drops
any validation or test row whose normalised text also occurs in training, for every dataset.
GoEmotions keeps its upstream train/dev/test, subject to that final pass. Affect labels are emotion categories for a
shadow model only: never crisis, danger, D4, SVI, band or routing labels. Text never leaves
the private roots and is never printed.
"""

import argparse
import csv
import re
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import external_corpus as xc
from . import governance
from ..nlp.transliterate import to_hinglish

AFFECT = ("neutral", "happy", "sad", "angry", "fearful")
CORPUS_VERSION = "textaffect-corpus-v2"
SPLIT_SEED = "sahay-textaffect-2026-09"
TRAINING_ROOT_ENV = "SAHAY_TRAINING_ROOT"
OUT_DIR = ("textaffect", "corpus-v2")

EMOINHINDI_MAP = {"anger": "angry", "fear": "fearful", "apprehensive": "fearful", "sad": "sad", "joy": "happy",
                  "neutral": "neutral"}
GOEMOTIONS_MAP = {"anger": "angry", "fear": "fearful", "nervousness": "fearful", "sadness": "sad", "joy": "happy",
                  "neutral": "neutral"}
GOEMOTIONS = {
    "dataset_id": "goemotions",
    "base_url": "https://raw.githubusercontent.com/google-research/google-research/master/goemotions/data/",
    "files": {"train.tsv": 3519053, "dev.tsv": 439059, "test.tsv": 436706, "emotions.txt": 248},
    "relative_dir": "corpus/text/english/goemotions",
    "pin_file": "sha256-pins.json",
}
GOEMOTIONS_SPLIT = {"train": "train", "dev": "val", "test": "test"}
MIN_TEXT_CHARS = 3
#: A repeated sentence keeps its majority label only if at least this share of its copies agree.
MAJORITY_SHARE = 2 / 3
#: Sentences whose word sets overlap at least this much (Jaccard) are one near-duplicate group
#: and always land in the same split. v2 without it still had 18% of test sentences at >= 0.8.
NEAR_DUPLICATE_JACCARD = 0.8
#: GoEmotions is mostly neutral. In train and val its neutral rows are capped at this multiple of
#: the largest other class (deterministic by hash); test stays complete (UAR is prior-invariant).
GOEMOTIONS_NEUTRAL_CAP = 2.0
_NORMALISE = re.compile(r"[\s\u0964\u0965.,!?;:'\"()\[\]{}\-\u2013\u2014\u2026]+")


class AffectCorpusError(Exception):
    """A refusal with a fixed message: no path and no text."""


# --- labels ------------------------------------------------------------------------------------


def emoinhindi_turn_label(labels: str, intensities: str) -> Tuple[Optional[str], str]:
    """(affect class or None, reason). ``labels`` and ``intensities`` are the raw comma lists."""
    names = [x.strip().lower() for x in str(labels or "").split(",") if x.strip()]
    levels = [x.strip() for x in str(intensities or "").split(",")]
    scored: Dict[str, float] = {}
    for i, name in enumerate(names):
        target = EMOINHINDI_MAP.get(name)
        if target is None:
            continue
        try:
            level = float(levels[i]) if i < len(levels) and levels[i] else 1.0
        except ValueError:
            level = 1.0
        scored[target] = max(scored.get(target, 0.0), level)
    if not scored:
        return None, "no_mapped_emotion"
    if len(scored) == 1:
        return next(iter(scored)), "single"
    best = max(scored.values())
    top = [c for c, v in scored.items() if v == best]
    return (top[0], "highest_intensity") if len(top) == 1 else (None, "tied_classes")


def goemotions_label(label_ids: str, names: Sequence[str]) -> Tuple[Optional[str], str]:
    ids = [x for x in str(label_ids or "").split(",") if x.strip()]
    if len(ids) != 1:
        return None, "multi_label"
    try:
        name = names[int(ids[0])]
    except (ValueError, IndexError):
        return None, "bad_label_id"
    target = GOEMOTIONS_MAP.get(name)
    return (target, "single") if target else (None, "unmapped_emotion")


def text_key(text: str) -> str:
    """Normalised form used for duplicate detection and splitting."""
    return _NORMALISE.sub(" ", str(text)).strip().lower()


def text_split(key: str) -> str:
    bucket = int(hashlib.sha256(f"{SPLIT_SEED}:{key}".encode("utf-8")).hexdigest()[:8], 16) % 100
    return "test" if bucket < 15 else "val" if bucket < 30 else "train"


def near_duplicate_groups(keys: Sequence[str], threshold: float = NEAR_DUPLICATE_JACCARD) -> Dict[str, str]:
    """Map each key to a group representative: union of pairs whose word-set Jaccard >= threshold."""
    parent = {k: k for k in keys}

    def find(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    sets = [(k, frozenset(k.split())) for k in keys]
    sets.sort(key=lambda kv: len(kv[1]))
    for i, (ki, si) in enumerate(sets):
        if not si:
            continue
        for kj, sj in sets[i + 1:]:
            if len(si) < threshold * len(sj):
                break                      # sorted by size: every later set is too large to reach the threshold
            inter = len(si & sj)
            if inter and inter / (len(si) + len(sj) - inter) >= threshold:
                ri, rj = find(ki), find(kj)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    return {k: find(k) for k in keys}


def enforce_split_disjoint(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """Drop validation or test rows whose normalised text also occurs in training (same language)."""
    train = {(r["language"], text_key(r["text"])) for r in rows if r["split"] == "train"}
    kept = [r for r in rows if r["split"] == "train" or (r["language"], text_key(r["text"])) not in train]
    return kept, len(rows) - len(kept)


# --- sources -------------------------------------------------------------------------------------


def _count(counter: Dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def emoinhindi_rows(records: Iterable[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """One row per distinct sentence (plus its Hinglish copy), labelled by majority, split by text."""
    dropped: Dict[str, int] = {}
    groups: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        for turn in rec.get("turns") or []:
            text = str(turn.get("text") or "").strip()
            if len(text) < MIN_TEXT_CHARS:
                _count(dropped, "too_short")
                continue
            label, reason = emoinhindi_turn_label(turn.get("raw_source_label"), turn.get("raw_source_intensity"))
            if label is None:
                _count(dropped, reason)
                continue
            key = text_key(text)
            g = groups.setdefault(key, {"text": text, "labels": {}, "speakers": {}, "rules": {}, "n": 0})
            g["n"] += 1
            _count(g["labels"], label)
            _count(g["speakers"], str(turn.get("speaker")))
            _count(g["rules"], reason)
    cluster = near_duplicate_groups(sorted(groups))
    rows: List[Dict[str, Any]] = []
    for key, g in sorted(groups.items()):
        label, votes = max(g["labels"].items(), key=lambda kv: (kv[1], kv[0]))
        if votes / g["n"] < MAJORITY_SHARE:
            dropped["conflicting_labels"] = dropped.get("conflicting_labels", 0) + g["n"]
            continue
        if g["n"] > 1:
            dropped["collapsed_duplicates"] = dropped.get("collapsed_duplicates", 0) + g["n"] - 1
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        group = hashlib.sha256(cluster[key].encode("utf-8")).hexdigest()[:16]
        base = {"dataset": "emoinhindi", "group": group, "split": text_split(cluster[key]), "label": f"affect:{label}",
                "label_rule": "majority" if len(g["labels"]) > 1 else max(g["rules"], key=g["rules"].get),
                "speaker": max(g["speakers"], key=g["speakers"].get), "copies": g["n"], "turn_index": None}
        rows.append({**base, "id": f"emoinhindi:{digest}:hi", "language": "hi", "script": "devanagari",
                     "text": g["text"], "derivation": "source"})
        romanised = to_hinglish(g["text"])
        if romanised != g["text"]:
            rows.append({**base, "id": f"emoinhindi:{digest}:hinglish", "language": "hinglish", "script": "latin",
                         "text": romanised, "derivation": "transliterated"})
    return rows, dropped


def goemotions_dir(root: Path) -> Path:
    return governance.resolve_under(root, GOEMOTIONS["relative_dir"])


def goemotions_rows(root: Path) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    base = goemotions_dir(root)
    verify_goemotions(root, strict=True)
    names = [n.strip() for n in (base / "emotions.txt").read_text(encoding="utf-8").splitlines() if n.strip()]
    rows: List[Dict[str, Any]] = []
    dropped: Dict[str, int] = {}
    for fname, split_name in (("train.tsv", "train"), ("dev.tsv", "dev"), ("test.tsv", "test")):
        reader = csv.reader(io.StringIO((base / fname).read_text(encoding="utf-8")), delimiter="\t",
                            quoting=csv.QUOTE_NONE)
        for n, parts in enumerate(reader):
            if len(parts) < 3:
                _count(dropped, "malformed_row")
                continue
            text, ids, cid = parts[0].strip(), parts[1], parts[2].strip()
            if len(text) < MIN_TEXT_CHARS:
                _count(dropped, "too_short")
                continue
            label, reason = goemotions_label(ids, names)
            if label is None:
                _count(dropped, reason)
                continue
            rows.append({"id": f"goemotions:{cid or split_name + str(n)}", "dataset": "goemotions",
                         "group": cid or f"{split_name}:{n}", "split": GOEMOTIONS_SPLIT[split_name],
                         "language": "en", "script": "latin", "text": text, "label": f"affect:{label}",
                         "label_rule": reason, "derivation": "source", "speaker": None, "turn_index": None})
    return cap_neutral(rows, dropped)


def cap_neutral(rows: List[Dict[str, Any]], dropped: Dict[str, int]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    out: List[Dict[str, Any]] = []
    for split in ("train", "val", "test"):
        part = [r for r in rows if r["split"] == split]
        if split == "test":
            out += part
            continue
        others: Dict[str, int] = {}
        for r in part:
            if r["label"] != "affect:neutral":
                _count(others, r["label"])
        cap = int(GOEMOTIONS_NEUTRAL_CAP * max(others.values(), default=0))
        neutral = sorted((r for r in part if r["label"] == "affect:neutral"),
                         key=lambda r: hashlib.sha256(f"{SPLIT_SEED}:{r['id']}".encode("utf-8")).hexdigest())
        out += [r for r in part if r["label"] != "affect:neutral"] + neutral[:cap]
        if len(neutral) > cap:
            dropped[f"neutral_capped_{split}"] = len(neutral) - cap
    return out, dropped


# --- GoEmotions fetch and verification -------------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_goemotions(root: Path) -> Dict[str, Any]:
    import urllib.request  # the only network use in this module, reached only by this command
    base = goemotions_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    pins: Dict[str, Any] = {}
    for name, size in GOEMOTIONS["files"].items():
        target = base / name
        if not (target.is_file() and target.stat().st_size == size):
            with urllib.request.urlopen(GOEMOTIONS["base_url"] + name, timeout=60) as resp:
                data = resp.read()
            target.write_bytes(data)
        data = target.read_bytes()
        pins[name] = {"bytes": len(data), "sha256": _sha256(data), "expected_bytes": size}
    pin_path = base / GOEMOTIONS["pin_file"]
    if not pin_path.is_file():
        pin_path.write_bytes(json.dumps(pins, indent=1, sort_keys=True).encode("utf-8"))
    report = verify_goemotions(root, strict=False)
    report["pins_sha256"] = _sha256(pin_path.read_bytes())
    return report


def verify_goemotions(root: Path, strict: bool) -> Dict[str, Any]:
    base = goemotions_dir(root)
    pin_path = base / GOEMOTIONS["pin_file"]
    if not pin_path.is_file():
        if strict:
            raise AffectCorpusError("GoEmotions is not fetched; run fetch-goemotions first")
        return {"dataset": "goemotions", "result": "not_fetched"}
    pins = json.loads(pin_path.read_text(encoding="utf-8"))
    bad = []
    for name, pin in pins.items():
        path = base / name
        if not path.is_file() or path.stat().st_size != pin["bytes"] or _sha256(path.read_bytes()) != pin["sha256"]:
            bad.append(name)
    size_changed = [n for n, p in pins.items() if p["bytes"] != p["expected_bytes"]]
    result = {"dataset": "goemotions", "files": len(pins), "mismatched": bad, "upstream_size_changed": size_changed,
              "result": "verified" if not bad else "integrity_failed"}
    if strict and bad:
        raise AffectCorpusError("GoEmotions files do not match their recorded sha256")
    return result


# --- build -------------------------------------------------------------------------------------------


def _counts(rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        _count(out, f"{r['dataset']}|{r['language']}|{r['split']}|{r['label']}")
    return dict(sorted(out.items()))


def build(datasets_root: Path, out_dir: Path, registry: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    reg = registry if registry is not None else governance.load_registry()
    manifest: Dict[str, Any] = {"version": CORPUS_VERSION, "split_seed": SPLIT_SEED, "affect_classes": list(AFFECT),
                                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "mappings": {"emoinhindi": EMOINHINDI_MAP, "goemotions": GOEMOTIONS_MAP},
                                "sources": {}}
    rows: List[Dict[str, Any]] = []

    rec = governance.select_for(reg, "emoinhindi", "training")
    records = xc.load_normalized(datasets_root, "emoinhindi", reg)
    if not records:
        raise AffectCorpusError("the normalised EmoInHindi records are missing; convert them first (Task 5)")
    emo, dropped = emoinhindi_rows(records)
    rows += emo
    manifest["sources"]["emoinhindi"] = {"basis": governance.use_basis(rec), "dialogues": len(records),
                                         "rows": len(emo), "dropped": dict(sorted(dropped.items()))}

    try:
        go_rec = governance.select_for(reg, "goemotions", "training")
        go, go_dropped = goemotions_rows(datasets_root)
        rows += go
        manifest["sources"]["goemotions"] = {"basis": governance.use_basis(go_rec), "rows": len(go),
                                             "dropped": dict(sorted(go_dropped.items()))}
    except (governance.GovernanceError, AffectCorpusError) as exc:
        manifest["sources"]["goemotions"] = {"skipped": str(exc)}

    rows, cross_split = enforce_split_disjoint(rows)
    manifest["cross_split_duplicates_dropped"] = cross_split
    out_dir.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
    (out_dir / "examples.jsonl").write_bytes(body)
    manifest.update({"examples": len(rows), "examples_sha256": _sha256(body), "counts": _counts(rows)})
    (out_dir / "manifest.json").write_bytes((json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False)
                                             + "\n").encode("utf-8"))
    return manifest


def training_out_dir(explicit: Optional[str] = None) -> Path:
    raw = explicit or os.environ.get(TRAINING_ROOT_ENV, "")
    if not raw.strip():
        raise AffectCorpusError(f"{TRAINING_ROOT_ENV} is not set and no --training-root was given; it has no default")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise AffectCorpusError(f"the directory named by {TRAINING_ROOT_ENV} does not exist")
    for parent in (root, *root.parents):
        if (parent / ".git").exists() and (parent / "ml" / "data" / "affect_corpus.py").is_file():
            raise AffectCorpusError(f"{TRAINING_ROOT_ENV} is inside a SAHAY checkout; private outputs stay outside Git")
    return root.joinpath(*OUT_DIR)


def summary(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    per: Dict[str, int] = {}
    for key, n in manifest["counts"].items():
        dataset, language, split, _label = key.split("|")
        per[f"{dataset}|{language}|{split}"] = per.get(f"{dataset}|{language}|{split}", 0) + n
    by_label: Dict[str, int] = {}
    for key, n in manifest["counts"].items():
        _d, language, _s, label = key.split("|")
        by_label[f"{language}|{label}"] = by_label.get(f"{language}|{label}", 0) + n
    return {"version": manifest["version"], "examples": manifest["examples"],
            "examples_sha256": manifest["examples_sha256"], "sources": manifest["sources"],
            "by_dataset_language_split": per, "by_language_label": dict(sorted(by_label.items()))}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.data.affect_corpus", description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=None, help="datasets root; defaults to SAHAY_DATASETS_ROOT")
    parser.add_argument("--training-root", default=None, help="defaults to SAHAY_TRAINING_ROOT")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch-goemotions")
    sub.add_parser("verify-goemotions")
    sub.add_parser("build")
    args = parser.parse_args(argv)
    root = governance.dataset_root(args.root)
    if args.cmd == "fetch-goemotions":
        out: Dict[str, Any] = fetch_goemotions(root)
    elif args.cmd == "verify-goemotions":
        out = verify_goemotions(root, strict=False)
    else:
        out = summary(build(root, training_out_dir(args.training_root)))
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0 if out.get("result", "verified") == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())
