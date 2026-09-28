"""AE-15 interpretable baseline (plan M14): a standard-library logistic regression beside Stage W.

    python -m ml.training.cli baseline-lr              # trains LR-W0 and LR-W2, then evaluates both
    python -m ml.training.cli baseline-lr --smoke 256  # tiny run into baseline-lr-smoke/

It answers one question for the comparison table: how much of the shadow MuRIL's result could a
bag-of-features linear model reach on exactly the same data? Everything except the model is
shared with Stage W:

- the same rows and masks (``stage_w.fictional_rows``, ``load_weak``, ``weak_draw``, ``ARMS``);
- the same fixed 0.5 threshold;
- the same evaluator (``stage_w_eval.score_model``), with the same evidence classes.

Model, fixed in advance and never tuned:
- **Features.** Hashed binary features: lower-cased word unigrams and bigrams, plus character
  trigrams inside each word (with boundary marks), which helps romanised Hinglish spelling
  variation. 2**18 buckets, scaled by 1/sqrt(active features).
- **Heads.** One independent logistic head per logit (9, as in Stage W), trained by SGD over
  the masked rows. Learning rate 0.2 / sqrt(epoch), L2 1e-6, 5 epochs, seed 13.
- **Class weighting.** A per-head positive weight = negatives / positives among the rows that
  supervise that head, bounded to [1, 8].
- **Interpretability.** The report lists each head's ten highest-weighted features, drawn only
  from features seen in the fictional corpus. It never lists features seen only in forum text.

Standard library only; no Torch, no NumPy. Shadow only, like Stage W.
"""

import math
import random
import re
import time
import zlib
from array import array
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from . import hardening as hx, metrics, paths, stage_w as sw

BUCKETS = 2 ** 18
HYPER = {"features": "word 1-2 grams + in-word char 3-grams, hashed (crc32) to 2**18, binary, 1/sqrt(n)",
         "epochs": 5, "lr": 0.2, "lr_schedule": "lr / sqrt(epoch)", "l2": 1e-6, "pos_weight_bounds": [1.0, 8.0],
         "seed": 13, "threshold": metrics.THRESHOLD}
ARMS = {"LR-W0": "W0", "LR-W2": "W2"}
ROOT = ("baseline-lr",)
SMOKE_ROOT = ("baseline-lr-smoke",)
_WORD = re.compile(r"\w+", re.UNICODE)


def feature_strings(text: str) -> List[str]:
    words = _WORD.findall(text.casefold())
    feats = [f"w:{w}" for w in words] + [f"b:{a}_{b}" for a, b in zip(words, words[1:])]
    for w in words:
        padded = f"<{w}>"
        feats += [f"c:{padded[i:i + 3]}" for i in range(len(padded) - 2)]
    return feats


def bucket(feature: str) -> int:
    return zlib.crc32(feature.encode("utf-8")) % BUCKETS


def vectorise(text: str) -> Tuple[List[int], float]:
    """Sorted unique buckets and the 1/sqrt(n) value every active feature takes."""
    idx = sorted({bucket(f) for f in feature_strings(text)})
    return idx, (1.0 / math.sqrt(len(idx)) if idx else 0.0)


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class LogReg:
    """Nine independent sparse logistic heads."""

    def __init__(self, n_heads: int) -> None:
        self.w = [array("d", bytes(8 * BUCKETS)) for _ in range(n_heads)]
        self.b = [0.0] * n_heads

    def logits(self, idx: Sequence[int], val: float) -> List[float]:
        return [b + val * sum(w[i] for i in idx) for w, b in zip(self.w, self.b)]

    def predict(self, rows: Sequence[Mapping[str, Any]]) -> List[List[float]]:
        out = []
        for r in rows:
            idx, val = vectorise(r["text"])
            out.append([_sigmoid(z) for z in self.logits(idx, val)])
        return out


def pos_weights(rows: Sequence[Mapping[str, Any]], n_heads: int) -> List[float]:
    lo, hi = HYPER["pos_weight_bounds"]
    out = []
    for h in range(n_heads):
        pos = sum(1 for r in rows if r["m"][h] and r["y"][h])
        neg = sum(1 for r in rows if r["m"][h] and not r["y"][h])
        out.append(round(min(max(neg / pos, lo), hi), 4) if pos else hi)
    return out


def train(train_rows: Sequence[Mapping[str, Any]], pools: Mapping[str, Sequence[Mapping[str, Any]]], arm: str,
          epochs: int, log: Any = print) -> Tuple[LogReg, Dict[str, Any]]:
    seed = HYPER["seed"]
    active = {t: pools[t] for t in sw.ARMS[arm]}
    model = LogReg(len(sw.LABELS))
    sample = list(train_rows) + (sw.weak_draw(active, len(train_rows), seed, 1) if active else [])
    pw = pos_weights(sample, len(sw.LABELS))
    cache: Dict[str, Tuple[List[int], float]] = {}
    history = []
    for epoch in range(1, epochs + 1):
        started = time.perf_counter()
        order = list(train_rows) + (sw.weak_draw(active, len(train_rows), seed, epoch) if active else [])
        random.Random(f"{seed}|{arm}|lr|{epoch}").shuffle(order)
        lr = HYPER["lr"] / math.sqrt(epoch)
        loss_sum, n_terms = 0.0, 0
        for r in order:
            key = r["id"]
            if key not in cache:
                cache[key] = vectorise(r["text"])
            idx, val = cache[key]
            for h, (y, m) in enumerate(zip(r["y"], r["m"])):
                if not m:
                    continue
                w = model.w[h]
                p = _sigmoid(model.b[h] + val * sum(w[i] for i in idx))
                weight = pw[h] if y else 1.0
                g = weight * (p - y)
                loss_sum += -weight * (math.log(max(p, 1e-12)) if y else math.log(max(1 - p, 1e-12)))
                n_terms += 1
                step = lr * g * val
                for i in idx:
                    w[i] -= step + lr * HYPER["l2"] * w[i]
                model.b[h] -= lr * g
        history.append({"epoch": epoch, "rows": len(order), "train_loss": round(loss_sum / max(1, n_terms), 5),
                        "seconds": round(time.perf_counter() - started, 1)})
        log(f"  {arm} (logistic) epoch {epoch}: rows {len(order)} loss {history[-1]['train_loss']} "
            f"({history[-1]['seconds']} s)")
    return model, {"history": history, "pos_weights": dict(zip(sw.LABELS, pw))}


def top_features(model: LogReg, vocabulary: Set[str], k: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    """Highest-weighted features per head, restricted to strings seen in the fictional corpus."""
    by_bucket: Dict[int, List[str]] = {}
    for f in vocabulary:
        by_bucket.setdefault(bucket(f), []).append(f)
    out = {}
    for h, name in enumerate(sw.LABELS):
        w = model.w[h]
        ranked = sorted(by_bucket, key=lambda i: w[i], reverse=True)[:k]
        out[name] = [{"features": sorted(by_bucket[i])[:3], "weight": round(w[i], 4)} for i in ranked if w[i] > 0]
    return out


def run(root: Path, *, smoke: Optional[int] = None, log: Any = print) -> Dict[str, Any]:
    from . import stage_w_eval as swe  # imported here: it reads the exposed fixtures only for evaluation
    is_smoke = smoke is not None
    suffix = "" if sw.FICTIONAL_VERSION == hx.VERSION else f"-{sw.FICTIONAL_VERSION}"
    base = (SMOKE_ROOT[0] + suffix,) if is_smoke else (ROOT[0] + suffix,)
    train_rows = sw.fictional_rows(hx.load_split(root, "train", sw.FICTIONAL_VERSION))
    pools = sw.load_weak(root, "train")
    if is_smoke:
        train_rows = train_rows[:smoke]
        pools = {t: p[:smoke] for t, p in pools.items()}
    vocabulary = {f for r in train_rows for f in feature_strings(r["text"])}
    data = swe.load_data(root, smoke)
    report: Dict[str, Any] = {"model_id": "interpretable_logistic_baseline", "hyperparameters": HYPER,
                              "fictional_corpus": sw.FICTIONAL_VERSION,
                              "calibrated": False, "authoritative": False, "smoke": is_smoke,
                              "evidence_classes": swe.EVIDENCE, "runs": []}
    for name, arm in ARMS.items():
        started = time.perf_counter()
        model, info = train(train_rows, pools, arm, 1 if is_smoke else HYPER["epochs"], log)
        scored = swe.score_model(data, model.predict)
        report["runs"].append({"arm": name, "stage_w_arm": arm, "seed": HYPER["seed"], **info,
                               "top_features_fictional_vocabulary": top_features(model, vocabulary),
                               "seconds": round(time.perf_counter() - started, 1), **scored})
        log(f"  {name}: holdout macro F1 {scored['holdout']['macro']['f1']}, exposed micro F1 dev "
            f"{scored['exposed']['dev']['model']['micro_f1']} / candidates {scored['exposed']['candidates']['model']['micro_f1']}")
    paths.write_json(paths.confined(root, *base, "reports", "evaluation.json"), report)
    return swe.summary({"selected": None, "smoke": is_smoke, "runs": report["runs"]})
