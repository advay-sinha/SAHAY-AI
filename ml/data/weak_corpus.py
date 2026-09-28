"""Stage W weak-supervision corpus (plan M14, EXT-129): source labels as training labels, with caveats.

    python -m ml.data.weak_corpus build [--training-root DIR]

It reads the private, already privacy-processed EXT-119 segment file
(``<SAHAY_TRAINING_ROOT>/corpora/external-ext119-v1/segments.jsonl``) and nothing else. It never
opens a raw dataset. For each source it keeps the windows whose source label has a documented
meaning and maps that label to ONE SAHAY training target through ``label_firewall.map_for_training``:

| Source | Source label -> target | Caveat carried |
|---|---|---|
| Reddit Suicide Detection | suicide / non-suicide -> ``crisis_self_harm`` 1 / 0 | subreddit of origin, not a human judgement |
| Hate-speech derivative | hate / not hate -> ``continuing_threat`` 1 / 0 | hate speech is not a threat |
| Dreaddit | stress / not stress -> ``D5`` 1 / 0 | crowd-annotated stress; not trauma or a diagnosis |

Every row is ``weak_supervision_from_source_label`` evidence. Nothing here makes a source label an
official SAHAY label, an evaluation label for the locked set, a routing decision or a product output.
The train and test buckets are the EXT-119 family-isolated ``aux_split`` values, so no duplicate
family crosses them. Standard library only; output is written beneath the training root only.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from . import governance as gov
from . import label_firewall as fw

TRAINING_ROOT_ENV = "SAHAY_TRAINING_ROOT"
CORPUS_NAME = "weak-ext129-v1"
SEGMENTS = ("corpora", "external-ext119-v1", "segments.jsonl")
SEGMENTS_MANIFEST = ("corpora", "external-ext119-v1", "manifest.json")
SALT = "sahay-weak-ext129-v1"

#: dataset -> SAHAY target, the source label -> (source family, target value) map, and bucket caps
#: per target value. ``None`` keeps every window. Reddit keeps only each post's first window.
SOURCES: Dict[str, Dict[str, Any]] = {
    "reddit_suicide_detection": {
        "target": "crisis_self_harm",
        "labels": {"source:reddit_suicide_detection:suicide": ("suicide_related", 1),
                   "source:reddit_suicide_detection:non-suicide": ("non_suicide", 0)},
        "caps": {"train": 10000, "test": 3000}, "first_window_only": True,
    },
    "hinglish_hate_speech_local_derivative": {
        "target": "continuing_threat",
        "labels": {"source:hinglish_hate_speech_local_derivative:1.0": ("hate_speech", 1),
                   "source:hinglish_hate_speech_local_derivative:0.0": ("not_hate_speech", 0)},
        "caps": {"train": None, "test": None}, "first_window_only": False,
    },
    "dreaddit": {
        "target": "D5",
        "labels": {"source:dreaddit:1": ("stress", 1), "source:dreaddit:0": ("other", 0)},
        "caps": {"train": None, "test": None}, "first_window_only": False,
    },
}
#: Caveats for mappings the firewall has no hard refusal for, written here so every row carries one.
EXTRA_CAVEATS = {
    ("non_suicide", "crisis_self_harm"): "a non-suicide subreddit post is not verified free of crisis language",
    ("suicide_related", "crisis_self_harm"): None,  # the firewall's own caveat applies
    ("stress", "D5"): "crowd-annotated stress (kappa 0.47) is everyday strain, not trauma or a diagnosis",
    ("other", "D5"): "a no-stress annotation is not an absence of trauma indicators",
    ("hate_speech", "continuing_threat"): None,
    ("not_hate_speech", "continuing_threat"): "absence of hate speech is not absence of threat",
}
BUCKETS = {"train": "train", "test": "test"}


class WeakCorpusError(Exception):
    """A refusal. Messages never contain an absolute path."""


def training_root(explicit: Optional[str] = None) -> Path:
    raw = explicit or os.environ.get(TRAINING_ROOT_ENV, "")
    if not raw.strip():
        raise WeakCorpusError(f"{TRAINING_ROOT_ENV} is not set and no --training-root was given; it has no default")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise WeakCorpusError(f"the directory named by {TRAINING_ROOT_ENV} does not exist")
    for parent in (root, *root.parents):
        if (parent / ".git").exists() and (parent / "ml" / "data" / "weak_corpus.py").is_file():
            raise WeakCorpusError(f"{TRAINING_ROOT_ENV} is inside a SAHAY checkout; private outputs stay outside Git")
    return root


def mappings(registry: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Governance selection plus one firewall-approved training mapping per (source label, target)."""
    out: Dict[str, Dict[str, Any]] = {}
    for dataset_id, spec in SOURCES.items():
        rec = gov.select_for(registry, dataset_id, "training")
        for raw, (family, value) in spec["labels"].items():
            m = fw.map_for_training(dataset_id, family, spec["target"], "training")
            caveat = m["caveat"] or EXTRA_CAVEATS.get((family, spec["target"]))
            if not caveat:
                raise WeakCorpusError(f"no caveat recorded for {family} -> {spec['target']}")
            out[raw] = {"dataset_id": dataset_id, "source_family": family, "target": spec["target"], "value": value,
                        "evidence_class": m["evidence_class"], "caveat": caveat, "basis": m["basis"],
                        "use_basis": gov.use_basis(rec)}
    return out


def _key(uid: str) -> str:
    return hashlib.sha256(f"{SALT}|{uid}".encode("utf-8")).hexdigest()


def select_rows(segments: Iterable[Mapping[str, Any]], maps: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Mapped rows, capped per (dataset, bucket, value) by a salted hash order (deterministic)."""
    pools: Dict[tuple, List[Dict[str, Any]]] = {}
    for s in segments:
        spec = SOURCES.get(s.get("dataset_id", ""))
        if spec is None or s.get("opaque_labels") or len(s.get("source_labels") or []) != 1:
            continue
        m = maps.get(s["source_labels"][0])
        bucket = BUCKETS.get(s.get("aux_split", ""))
        if m is None or bucket is None or (spec["first_window_only"] and s.get("window") != 0):
            continue
        row = {"uid": s["uid"], "family": s["family"], "dataset_id": s["dataset_id"], "language": s["language"],
               "script": s["script"], "text": s["text"], "target": m["target"], "value": m["value"], "split": bucket,
               "weight": s.get("weight", 1.0), "evidence_class": m["evidence_class"]}
        pools.setdefault((s["dataset_id"], bucket, m["value"]), []).append(row)
    rows: List[Dict[str, Any]] = []
    for (dataset_id, bucket, _value), pool in sorted(pools.items()):
        pool.sort(key=lambda r: _key(r["uid"]))
        cap = SOURCES[dataset_id]["caps"][bucket]
        rows += pool if cap is None else pool[:cap]
    families = {}
    for r in rows:
        families.setdefault(r["family"], set()).add(r["split"])
    crossing = [f for f, splits in families.items() if len(splits) > 1]
    if crossing:
        raise WeakCorpusError(f"{len(crossing)} duplicate families cross the train/test buckets")
    return sorted(rows, key=lambda r: (r["split"], r["dataset_id"], _key(r["uid"])))


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".partial")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)


def counts(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for r in rows:
        k = f"{r['dataset_id']}|{r['split']}"
        out.setdefault(k, {"0": 0, "1": 0})[str(r["value"])] += 1
    return dict(sorted(out.items()))


def build(root: Path, registry: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    registry = registry or gov.load_registry()
    maps = mappings(registry)
    seg_path = root.joinpath(*SEGMENTS)
    if not seg_path.is_file():
        raise WeakCorpusError("the EXT-119 segment file is missing; build it first (ml.data.training_corpus)")
    ext_manifest = json.loads(root.joinpath(*SEGMENTS_MANIFEST).read_text(encoding="utf-8"))
    seg_sha = _sha(seg_path)
    if seg_sha != ext_manifest.get("segments_sha256"):
        raise WeakCorpusError("the EXT-119 segment file does not match its manifest hash")
    rows = select_rows(_read_jsonl(seg_path), maps)
    out = root / "corpora" / CORPUS_NAME
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for split in ("train", "test"):
        path = out / f"{split}.jsonl"
        _write_jsonl(path, (r for r in rows if r["split"] == split))
        files[f"{split}.jsonl"] = _sha(path)
    manifest = {
        "corpus": CORPUS_NAME, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "evidence_class": fw.WEAK_SUPERVISION, "basis": "EXT-129",
        "artifact_class": "quarantined_research_artifact",
        "source_segments_sha256": seg_sha, "files_sha256": files, "counts": counts(rows),
        "mappings": {raw: {k: v for k, v in m.items()} for raw, m in sorted(maps.items())},
        "never": sorted(fw.NEVER_EVEN_FOR_TRAINING),
        "note": ("source labels used as weak training labels only; metrics against them are weak-supervision "
                 "evidence, never human-judged SAHAY ground truth"),
    }
    tmp = out / "manifest.json.partial"
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, out / "manifest.json")
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.data.weak_corpus", description=__doc__.split("\n")[0])
    parser.add_argument("--training-root", help=f"overrides {TRAINING_ROOT_ENV}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    args = parser.parse_args(argv)
    try:
        manifest = build(training_root(args.training_root))
    except (WeakCorpusError, gov.GovernanceError, fw.LabelFirewallError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({k: manifest[k] for k in ("corpus", "evidence_class", "counts", "files_sha256")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
