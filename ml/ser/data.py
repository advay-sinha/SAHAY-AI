"""SER training data: joins the preprocessing outputs and builds feature rows. Standard library only.

Reads ``clips.jsonl`` (labels, actor, sex, split) and ``features.jsonl`` (status, prosody,
quality) beneath ``<SAHAY_TRAINING_ROOT>/ser/corpus-v1``. Only clips with ``status == "ok"``
are used; excluded clips are counted by class so losses are visible, never silent.

Speaker normalisation: prosody features are z-scored per actor, the training-time analogue of
the deployed rule (deviation from the caller's own in-session baseline). The statistics use
only the actor's own feature values, never labels, so nothing about a test label leaks.
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

AFFECT = ("neutral", "happy", "sad", "angry", "fearful")
PROSODY_FEATURES = ("f0_median_st", "f0_std_st", "f0_range_st", "f0_perturbation", "voiced_ratio",
                    "rms_mean_db", "rms_std_db", "pause_ratio", "pause_count", "mean_pause_s", "max_pause_s",
                    "speech_s", "snr_db")


class DataError(Exception):
    """A refusal with a fixed message: no path, no audio."""


def _read(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        raise DataError(f"{path.name} is missing; run the preprocessing steps first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_rows(corpus: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Usable rows (clip metadata + prosody + quality), and a report of what was excluded."""
    clips = {c["clip_id"]: c for c in _read(corpus / "clips.jsonl")}
    rows, excluded = [], {}
    for f in _read(corpus / "features.jsonl"):
        clip = clips.get(f["clip_id"])
        if clip is None:
            raise DataError("features.jsonl names a clip that clips.jsonl does not")
        if f.get("status") != "ok":
            key = f"{clip['dataset']}|{clip['label']}|{f.get('status')}"
            excluded[key] = excluded.get(key, 0) + 1
            continue
        rows.append({**clip, "prosody": f["prosody"], "quality": f["quality"], "speech_s": f["speech_s"],
                     "audio_rel": f["audio_rel"], "affect": clip["label"].split(":", 1)[1]})
    return rows, {"usable": len(rows), "excluded": dict(sorted(excluded.items()))}


def prosody_vector(row: Mapping[str, Any]) -> List[Optional[float]]:
    p, q = row["prosody"], row["quality"]
    f0 = p.get("f0_median_hz")
    values = {
        "f0_median_st": 12.0 * math.log2(f0 / 100.0) if f0 else None,
        "f0_std_st": p.get("f0_std_st"), "f0_range_st": p.get("f0_range_st"),
        "f0_perturbation": p.get("f0_perturbation"), "voiced_ratio": p.get("voiced_ratio"),
        "rms_mean_db": p.get("rms_mean_db"), "rms_std_db": p.get("rms_std_db"),
        "pause_ratio": p.get("pause_ratio"), "pause_count": p.get("pause_count"),
        "mean_pause_s": p.get("mean_pause_s"), "max_pause_s": p.get("max_pause_s"),
        "speech_s": row.get("speech_s"), "snr_db": q.get("snr_db"),
    }
    return [None if values[k] is None else float(values[k]) for k in PROSODY_FEATURES]


def _mean_std(values: Sequence[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 1.0
    m = sum(values) / len(values)
    var = sum((v - m) ** 2 for v in values) / len(values)
    return m, math.sqrt(var) if var > 1e-12 else 1.0


def normalise(rows: Sequence[Mapping[str, Any]], *, per_speaker: bool,
              train_ids: Optional[set] = None) -> List[List[float]]:
    """Z-scored prosody vectors with missing values set to 0 (the mean) plus a missing flag each.

    ``per_speaker``: statistics from each actor's own clips. Otherwise: statistics from the
    training rows only (``train_ids``), applied to every row.
    """
    raw = [prosody_vector(r) for r in rows]
    n_feat = len(PROSODY_FEATURES)
    groups: Dict[str, List[int]] = {}
    for i, r in enumerate(rows):
        key = r["actor"] if per_speaker else "__all__"
        groups.setdefault(key, []).append(i)
    stats: Dict[str, List[Tuple[float, float]]] = {}
    for key, idx in groups.items():
        basis = idx if per_speaker else [i for i in idx if train_ids is None or rows[i]["clip_id"] in train_ids]
        stats[key] = [_mean_std([raw[i][j] for i in basis if raw[i][j] is not None]) for j in range(n_feat)]
    out = []
    for i, r in enumerate(rows):
        st = stats[r["actor"] if per_speaker else "__all__"]
        vec = []
        for j in range(n_feat):
            v = raw[i][j]
            vec.append(0.0 if v is None else (v - st[j][0]) / st[j][1])
        vec += [1.0 if raw[i][j] is None else 0.0 for j in range(n_feat)]
        out.append(vec)
    return out


def class_weights(labels: Sequence[str], classes: Sequence[str] = AFFECT) -> List[float]:
    """Inverse-frequency weights normalised to mean 1; a class absent from training gets 0."""
    counts = [sum(1 for l in labels if l == c) for c in classes]
    present = [c for c in counts if c]
    if not present:
        raise DataError("no training labels")
    raw = [(len(labels) / (len(present) * c)) if c else 0.0 for c in counts]
    mean = sum(w for w in raw if w) / len(present)
    return [round(w / mean, 6) for w in raw]


def select(rows: Sequence[Mapping[str, Any]], split: str, datasets: Sequence[str]) -> List[int]:
    return [i for i, r in enumerate(rows) if r["split"] == split and r["dataset"] in datasets]


TRAIN_REGIMES = {
    # regime -> datasets whose train/val splits train and select the model
    "both": ("crema_d", "ravdess_audio_speech"),
    "crema": ("crema_d",),
}
