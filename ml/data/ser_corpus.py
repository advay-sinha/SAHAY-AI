"""SER corpus manifest: labels, speaker metadata and actor-disjoint splits (plan M12c, run R2).

    python -m ml.data.ser_corpus build

Standard library only. The command reads the verified RAVDESS and CREMA-D audio beneath
``SAHAY_DATASETS_ROOT``, but only if the registry approves them for training (EXT-003 /
EXT-104). It writes ``<SAHAY_TRAINING_ROOT>/ser/corpus-v1/clips.jsonl`` and ``manifest.json``.
No audio is copied here; ``ml.ser.preprocess`` reads the clip list.

Labels
    Only five classes are kept, as ``affect:neutral|happy|sad|angry|fearful``. Every other
    source emotion (RAVDESS calm, surprised and disgust; CREMA-D disgust) is dropped, never
    folded into another class. The source label is kept verbatim as ``source:<dataset>:<code>``.
    Affect labels are acted-emotion categories. They are never crisis, danger, distress, SVI, band
    or D4 labels (``d4_acoustic_distress`` stays prohibited in the registry).

Splits
    Actor-disjoint and stratified by sex, deterministic from ``SPLIT_SEED``. No actor appears
    in two splits of the same corpus. The cross-corpus check (train on CREMA-D, test on RAVDESS)
    uses these same per-corpus splits.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from . import governance

CORPUS_VERSION = "ser-corpus-v1"
SPLIT_SEED = "sahay-ser-2026-09"
AFFECT = ("neutral", "happy", "sad", "angry", "fearful")
TRAINING_ROOT_ENV = "SAHAY_TRAINING_ROOT"
OUT_DIR = ("ser", "corpus-v1")

#: RAVDESS emotion code (3rd filename field) -> affect class; absent = dropped.
RAVDESS_EMOTION = {"01": "neutral", "03": "happy", "04": "sad", "05": "angry", "06": "fearful"}
RAVDESS_DROPPED = {"02": "calm", "07": "disgust", "08": "surprised"}
#: CREMA-D emotion code (3rd filename field) -> affect class; absent = dropped.
CREMA_EMOTION = {"NEU": "neutral", "HAP": "happy", "SAD": "sad", "ANG": "angry", "FEA": "fearful"}
CREMA_DROPPED = {"DIS": "disgust"}

RAVDESS_DIR = "corpus/audio/ravdess/extracted"
CREMA_AUDIO = "corpus/audio/crema_d/CREMA-D/AudioWAV"
CREMA_DEMOGRAPHICS = "corpus/audio/crema_d/CREMA-D/VideoDemographics.csv"

#: Share of each sex's actors that go to validation and to test (the rest train).
SPLIT_FRACTIONS = {"ravdess_audio_speech": (4 / 24, 4 / 24), "crema_d": (0.15, 0.15)}


class CorpusError(Exception):
    """A refusal with a fixed message: no path and no file content."""


# --- filename parsing -------------------------------------------------------------------------


def parse_ravdess(stem: str) -> Optional[Dict[str, Any]]:
    """``03-01-05-01-02-01-12`` -> fields; None for anything that is not audio-only speech."""
    parts = stem.split("-")
    if len(parts) != 7 or not all(p.isdigit() and len(p) == 2 for p in parts):
        raise CorpusError("unexpected RAVDESS filename shape")
    modality, channel, emotion, intensity, statement, repetition, actor = parts
    if modality != "03" or channel != "01":
        return None
    actor_n = int(actor)
    return {
        "actor": f"ravdess:{actor_n:02d}",
        "sex": "male" if actor_n % 2 == 1 else "female",
        "source_label": f"source:ravdess:{emotion}",
        "affect": RAVDESS_EMOTION.get(emotion),
        "dropped_as": RAVDESS_DROPPED.get(emotion),
        "intensity": {"01": "normal", "02": "strong"}.get(intensity, "unknown"),
        "sentence": f"ravdess:{statement}",
        "repetition": int(repetition),
    }


def parse_crema(stem: str) -> Dict[str, Any]:
    """``1001_DFA_ANG_XX`` -> fields."""
    parts = stem.split("_")
    if len(parts) != 4 or not parts[0].isdigit() or len(parts[2]) != 3:
        raise CorpusError("unexpected CREMA-D filename shape")
    actor, sentence, emotion, level = parts
    return {
        "actor": f"crema_d:{actor}",
        "source_label": f"source:crema_d:{emotion}",
        "affect": CREMA_EMOTION.get(emotion),
        "dropped_as": CREMA_DROPPED.get(emotion),
        "intensity": {"LO": "low", "MD": "medium", "HI": "high"}.get(level, "unspecified"),
        "sentence": f"crema_d:{sentence}",
    }


def read_crema_demographics(path: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sex = (row.get("Sex") or "").strip().lower()
            age = (row.get("Age") or "").strip()
            out[f"crema_d:{row['ActorID'].strip()}"] = {
                "sex": sex if sex in ("male", "female") else "unknown",
                "age_band": _age_band(int(age)) if age.isdigit() else "unknown",
                "race": (row.get("Race") or "unknown").strip() or "unknown",
            }
    return out


def _age_band(age: int) -> str:
    for hi, band in ((29, "20-29"), (39, "30-39"), (49, "40-49"), (59, "50-59")):
        if age <= hi:
            return band if age >= hi - 9 else "under-20"
    return "60+"


# --- splits -----------------------------------------------------------------------------------


def _order_key(actor: str) -> str:
    return hashlib.sha256(f"{SPLIT_SEED}:{actor}".encode("utf-8")).hexdigest()


def assign_splits(actors: Mapping[str, str], val_fraction: float, test_fraction: float) -> Dict[str, str]:
    """Actor -> split. Each sex is ordered by a seeded hash and cut into test, val and train."""
    by_sex: Dict[str, List[str]] = {}
    for actor, sex in actors.items():
        by_sex.setdefault(sex, []).append(actor)
    out: Dict[str, str] = {}
    for sex in sorted(by_sex):
        ordered = sorted(by_sex[sex], key=_order_key)
        n = len(ordered)
        n_test = max(1, round(n * test_fraction)) if n >= 3 else 0
        n_val = max(1, round(n * val_fraction)) if n >= 3 else 0
        for i, actor in enumerate(ordered):
            out[actor] = "test" if i < n_test else "val" if i < n_test + n_val else "train"
    return out


# --- build ------------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _collect(root: Path, dataset: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    rows: List[Dict[str, Any]] = []
    dropped: Dict[str, int] = {}
    if dataset == "ravdess_audio_speech":
        base = governance.resolve_under(root, RAVDESS_DIR)
        files = sorted(base.glob("Actor_*/*.wav"))
        demo: Dict[str, Dict[str, Any]] = {}
    else:
        base = governance.resolve_under(root, CREMA_AUDIO)
        files = sorted(base.glob("*.wav"))
        demo = read_crema_demographics(governance.resolve_under(root, CREMA_DEMOGRAPHICS))
    for path in files:
        fields = parse_ravdess(path.stem) if dataset == "ravdess_audio_speech" else parse_crema(path.stem)
        if fields is None:
            dropped["not_audio_speech"] = dropped.get("not_audio_speech", 0) + 1
            continue
        if fields["affect"] is None:
            key = fields["dropped_as"] or "unmapped"
            dropped[key] = dropped.get(key, 0) + 1
            continue
        fields.update(demo.get(fields["actor"], {}))
        fields.setdefault("sex", "unknown")
        rel = path.resolve().relative_to(root).as_posix()
        rows.append({
            "clip_id": f"{dataset}:{path.stem}",
            "dataset": dataset,
            "source_rel": rel,
            "source_sha256": _sha256(path),
            "label": f"affect:{fields.pop('affect')}",
            **{k: v for k, v in fields.items() if k != "dropped_as"},
        })
    return rows, dropped


def build(datasets_root: Path, out_dir: Path, registry: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    reg = registry if registry is not None else governance.load_registry()
    manifest: Dict[str, Any] = {"version": CORPUS_VERSION, "split_seed": SPLIT_SEED, "affect_classes": list(AFFECT),
                                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                # Private file beneath the training root (never in Git): the only place
                                # ml.ser learns where the source audio lives.
                                "datasets_root": str(Path(datasets_root).resolve()),
                                "datasets": {}}
    all_rows: List[Dict[str, Any]] = []
    for dataset in ("ravdess_audio_speech", "crema_d"):
        rec = governance.select_for(reg, dataset, "training")  # refuses anything not approved
        rows, dropped = _collect(datasets_root, dataset)
        actors = {r["actor"]: r["sex"] for r in rows}
        val_f, test_f = SPLIT_FRACTIONS[dataset]
        splits = assign_splits(actors, val_f, test_f)
        for r in rows:
            r["split"] = splits[r["actor"]]
        manifest["datasets"][dataset] = {
            "registry_sha256": rec["sha256"],
            "clips": len(rows),
            "dropped": dict(sorted(dropped.items())),
            "actors": len(actors),
            "actors_by_split": {s: sorted(a for a, v in splits.items() if v == s) for s in ("train", "val", "test")},
            "clips_by_split_and_label": _counts(rows, ("split", "label")),
            "clips_by_split_and_sex": _counts(rows, ("split", "sex")),
        }
        all_rows.extend(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in all_rows).encode("utf-8")
    (out_dir / "clips.jsonl").write_bytes(body)
    manifest["clips_sha256"] = hashlib.sha256(body).hexdigest()
    manifest["clips_total"] = len(all_rows)
    (out_dir / "manifest.json").write_bytes((json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    return manifest


def _counts(rows: Iterable[Mapping[str, Any]], keys: Tuple[str, ...]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        k = "|".join(str(r[x]) for x in keys)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def training_out_dir(explicit: Optional[str] = None) -> Path:
    raw = explicit or os.environ.get(TRAINING_ROOT_ENV, "")
    if not raw.strip():
        raise CorpusError(f"{TRAINING_ROOT_ENV} is not set and no --training-root was given; it has no default")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise CorpusError(f"the directory named by {TRAINING_ROOT_ENV} does not exist")
    for parent in (root, *root.parents):
        if (parent / ".git").exists() and (parent / "ml" / "data" / "ser_corpus.py").is_file():
            raise CorpusError(f"{TRAINING_ROOT_ENV} is inside a SAHAY checkout; private outputs stay outside Git")
    return root.joinpath(*OUT_DIR)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.data.ser_corpus", description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=None, help="datasets root; defaults to SAHAY_DATASETS_ROOT")
    parser.add_argument("--training-root", default=None, help="defaults to SAHAY_TRAINING_ROOT")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    args = parser.parse_args(argv)
    manifest = build(governance.dataset_root(args.root), training_out_dir(args.training_root))
    summary = {"version": manifest["version"], "clips_total": manifest["clips_total"],
               "clips_sha256": manifest["clips_sha256"],
               "datasets": {k: {"clips": v["clips"], "actors": v["actors"], "dropped": v["dropped"],
                                "actors_per_split": {s: len(a) for s, a in v["actors_by_split"].items()}}
                            for k, v in manifest["datasets"].items()}}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
