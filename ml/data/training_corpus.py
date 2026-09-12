"""EXT-119 training corpus: the Task 5 processed external text, prepared for local MuRIL training.

    python -m ml.data.training_corpus build --ext119-local-training --acknowledge "<sentence>" \
        [--operator <name>]

This is the only Task 7 module that reads external datasets. It turns the Task 5 privacy-processed
normalised records into one private, deterministic segment file beneath ``SAHAY_TRAINING_ROOT``
for Stage A (masked-language modelling) and Stage B (source-namespaced auxiliary heads). The
trainer in ``ml.training`` reads only that file and never touches a dataset.

Governance
----------
EXT-119 (``docs/EXTERNAL_DECISIONS.md``) authorises local, offline experimental training on these
licence-pending datasets. It resolves no licence and no privacy question. Every run therefore
needs the recorded APPROVED decision **and** a per-run flag with the exact acknowledgement
sentence; each use is appended to the private override log. The registry is not changed: the
datasets stay ``licence_pending`` and every output stays a ``quarantined_research_artifact``.
The Task 5 exploratory override still refuses training; EXT-119 is a separate, narrower basis.

What is produced
----------------
* Every usable normalised record, verified against its Task 5 manifest hash first.
* The 3,199 nonblank hate-speech rows that have no source label (Task 5 excluded them from the
  labelled output), re-read through the same pinned, hash-checked source and the same privacy
  redaction, for masked-language modelling only. Blank rows are counted, never invented.
* Text split into windows of at most ``WINDOW_CHARS`` characters on word (or, for dialogues,
  turn) boundaries, so a window fits a 128-token encoder input.
* Duplicate families (Task 5 exact/near links plus identical text across datasets), each window
  weighted ``1 / family size`` so repeated text gains no accidental extra influence.
* A deterministic family-level partition: ``mlm_validation`` (about 0.5%) for held-out loss, and
  an auxiliary ``test`` bucket (about 10%) for source-head metrics. No family crosses partitions.
* Source labels only in their ``source:<dataset>:<value>`` namespace, never a SAHAY label.
  Sentiment classes are opaque, so they get no auxiliary task.

CREMA-D is checked and reported unavailable: its local media are Git LFS pointer files.
Nothing here prints text; the manifest holds counts, hashes and ids only.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from . import archive_safety as az, external_corpus as xc, governance as gov, inventory as inv
from . import label_firewall as fw

TRAINING_ROOT_ENV = "SAHAY_TRAINING_ROOT"
CORPUS_NAME = "external-ext119-v1"
CORPUS_SCHEMA = "sahay-ext119-training-segment"
CORPUS_SCHEMA_VERSION = "1.0.0"
DECISION_ID = "EXT-119"
DECISIONS_PATH = xc.REPO / "docs" / "EXTERNAL_DECISIONS.md"
GOVERNANCE_BASIS = "ext119_local_experimental_training"
EXT119_FLAG = "--ext119-local-training"
EXT119_ACKNOWLEDGEMENT = (
    "I invoke EXT-119 for local offline experimental training on licence-pending quarantined research "
    "datasets. Licensing and privacy approval remain unresolved. Outputs stay private, are never "
    "redistributed or published, and are never official evaluation evidence or victim-facing.")
DATASETS = ("reddit_suicide_detection", "dreaddit", "emoinhindi", "hinglish_hate_speech_local_derivative",
            "hinglish_sentiment_kaggle")
#: Datasets whose label meaning is documented well enough for a namespaced auxiliary head.
AUX_TASKS = {
    "reddit_suicide_detection": "single_label",   # subreddit membership, not a clinical judgement
    "dreaddit": "single_label",                   # annotated stress, not crisis
    "emoinhindi": "multi_label",                  # annotated emotions, not severity
    "hinglish_hate_speech_local_derivative": "single_label",
}
#: The sentiment classes 0/1/2 have no published meaning: opaque, no auxiliary task.
OPAQUE_LABELS = ("hinglish_sentiment_kaggle",)
#: Datasets whose every window joins the coverage pass. The (very large) suicide corpus joins
#: with its first window per record; its later windows are reached by the balanced phase.
ALL_WINDOWS_IN_COVERAGE = ("dreaddit", "emoinhindi", "hinglish_hate_speech_local_derivative",
                           "hinglish_sentiment_kaggle")
WINDOW_CHARS = 480
MLM_VALIDATION_PER_MILLE = 5
AUX_TEST_PER_MILLE = 100
CREMA_TOP_LEVEL = "CREMA-D-1.0"
EXACT_KEYS_FILE = "exact_keys.txt"
SEED = "sahay-ext119-v1"


class CorpusRefused(Exception):
    """A governance or integrity refusal. Messages carry no text and no absolute path."""


# --- governance ------------------------------------------------------------------------------


def decision_block(path: Path = DECISIONS_PATH) -> Optional[str]:
    """The fenced EXT-119 block of the decision log, or None."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    for block in re.findall(r"```text\n(.*?)\n```", text, re.S):
        if DECISION_ID in block:
            return block
    return None


def verify_decision(path: Path = DECISIONS_PATH) -> Dict[str, Any]:
    block = decision_block(path)
    if block is None:
        raise CorpusRefused(f"{DECISION_ID} is not recorded in docs/EXTERNAL_DECISIONS.md")
    if not re.search(r"^Decision:\s+APPROVED\s*$", block, re.M):
        raise CorpusRefused(f"{DECISION_ID} is recorded but not APPROVED")
    return {"decision": DECISION_ID, "status": "APPROVED",
            "sha256": hashlib.sha256(block.encode("utf-8")).hexdigest()}


def authorise(acknowledgement: Optional[str], registry: Mapping[str, Any]) -> Dict[str, Any]:
    decision = verify_decision()
    if acknowledgement != EXT119_ACKNOWLEDGEMENT:
        raise CorpusRefused(f"{EXT119_FLAG} needs the exact EXT-119 acknowledgement sentence")
    for dataset_id in DATASETS:
        rec = gov.get(registry, dataset_id)
        if rec["review_status"] != "licence_pending":
            raise CorpusRefused(f"{dataset_id} is {rec['review_status']}; EXT-119 covers licence_pending data only")
    return {"basis": GOVERNANCE_BASIS, **decision, "licence_approved": False, "privacy_approved": False,
            "artifact_class": xc.ARTIFACT_CLASS}


def training_root(explicit: Optional[str] = None) -> Path:
    raw = explicit or os.environ.get(TRAINING_ROOT_ENV, "")
    if not raw.strip():
        raise CorpusRefused(f"{TRAINING_ROOT_ENV} is not set and no --training-root was given; it has no default")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise CorpusRefused(f"the directory named by {TRAINING_ROOT_ENV} does not exist")
    if xc.inside_sahay_worktree(root):
        raise CorpusRefused(f"{TRAINING_ROOT_ENV} is inside a SAHAY checkout; private outputs stay outside Git")
    return root


def corpus_dir(training: Path) -> Path:
    target = (training / "corpora" / CORPUS_NAME).resolve()
    target.relative_to(training)
    return target


# --- text windows ------------------------------------------------------------------------------


def _split_words(text: str, limit: int) -> List[str]:
    windows: List[str] = []
    current = ""
    for word in text.split():
        while len(word) > limit:  # a single unbroken run longer than a window
            if current:
                windows.append(current)
                current = ""
            windows.append(word[:limit])
            word = word[limit:]
        candidate = f"{current} {word}" if current else word
        if len(candidate) > limit:
            windows.append(current)
            current = word
        else:
            current = candidate
    if current:
        windows.append(current)
    return windows


def text_windows(text: str, limit: int = WINDOW_CHARS) -> List[str]:
    return _split_words(text, limit) or []


def dialogue_windows(turns: Sequence[Mapping[str, Any]], limit: int = WINDOW_CHARS
                     ) -> List[Tuple[str, List[int]]]:
    """Consecutive turns packed into windows; returns (text, turn indexes) pairs."""
    out: List[Tuple[str, List[int]]] = []
    current, members = "", []
    for i, turn in enumerate(turns):
        text = " ".join(str(turn.get("text", "")).split())
        if not text:
            continue
        pieces = _split_words(text, limit) if len(text) > limit else [text]
        for piece in pieces:
            candidate = f"{current} \n {piece}" if current else piece
            if current and len(candidate) > limit:
                out.append((current, members))
                current, members = piece, [i]
            else:
                current = candidate
                members = members + [i] if i not in members else members
    if current:
        out.append((current, members))
    return out


# --- families and partitions -------------------------------------------------------------------


class Families:
    """Union-find over duplicate links; the root id names the family."""

    def __init__(self) -> None:
        self.parent: Dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def bucket(family: str, salt: str = SEED) -> int:
    return int(hashlib.sha256(f"{salt}|{family}".encode()).hexdigest()[:8], 16) % 1000


def partition_of(family: str) -> Tuple[str, str]:
    b = bucket(family)
    mlm = "mlm_validation" if b < MLM_VALIDATION_PER_MILLE else "train"
    aux = "test" if b < AUX_TEST_PER_MILLE else "train"
    return mlm, aux


# --- sources -----------------------------------------------------------------------------------


def namespaced(dataset_id: str, labels: Iterable[str]) -> List[str]:
    """Keep a window's labels only if each is this dataset's own ``source:<dataset>:<value>`` category.

    Uses the firewall's own constructor (``label_firewall.source_category``) as the reference form
    and refuses any label that is outside the namespace or collides with a SAHAY category name.
    """
    prefix = fw.source_category(dataset_id, "x")[:-1]  # "source:<dataset>:" exactly as the firewall builds it
    out = sorted(set(labels))
    for lab in out:
        value = lab[len(prefix):] if lab.startswith(prefix) else None
        if not value or fw.source_category(dataset_id, value) != lab or fw.is_sahay_category(value):
            raise CorpusRefused(f"{dataset_id}: a label outside its source namespace was refused")
    return out


def verify_normalized(root: Path, dataset_id: str, registry: Mapping[str, Any]) -> Tuple[Path, Dict[str, Any]]:
    manifest = xc.load_manifest(root, dataset_id, registry)
    if manifest is None:
        raise CorpusRefused(f"{dataset_id}: no finalised Task 5 output is present")
    path = xc.output_dir(root, dataset_id, manifest["source_sha256"]) / "records.jsonl"
    digest = az.sha256_file(path)
    if digest != manifest["records_sha256"]:
        raise CorpusRefused(f"{dataset_id}: normalised records do not match their manifest hash")
    return path, manifest


def unlabelled_rows(root: Path, dataset_id: str, registry: Mapping[str, Any], manifest: Mapping[str, Any],
                    counts: Counter) -> Iterator[Dict[str, Any]]:
    """Nonblank rows without a source label, privacy-processed exactly as Task 5 processes text."""
    rec = gov.get(registry, dataset_id)
    spec = xc.SPECS[dataset_id]
    path, file_sha, _ = xc.resolve_source(root, rec, spec)
    if file_sha != manifest["source_sha256"]:
        raise CorpusRefused(f"{dataset_id}: source file hash differs from the Task 5 manifest")
    for n, fields in xc.read_rows(path, spec):
        if "__malformed__" in fields:
            counts["malformed_row"] += 1
            continue
        if xc._has_label(fields.get(spec["label_column"])):
            continue  # labelled rows are already in the normalised output
        text = fields.get(spec["text_column"])
        if not isinstance(text, str) or not text.strip():
            counts["blank_unlabelled_row"] += 1
            continue
        clean, redactions = xc.redact(text.strip())
        row_sha = xc.sha256_text(xc.canonical({"file": file_sha, "row": n, "fields": fields}))
        counts["unlabelled_rows_used"] += 1
        yield {"record_id": f"EXT:{dataset_id}:unlabelled:{row_sha[:16]}", "dataset_id": dataset_id,
               "text": clean, "language": xc.normalise_language(fields.get(spec.get("language_column") or "")),
               "script": xc.script_of(clean), "exact_key": xc.exact_key(clean), "duplicate_of": None,
               "source_label_category": [], "privacy_findings": sorted(redactions)}


def crema_status(root: Path) -> Dict[str, Any]:
    base = gov.resolve_under(root, CREMA_TOP_LEVEL)
    media = stubs = 0
    if base.is_dir():
        for dirpath, _, files in os.walk(base):
            for name in files:
                p = Path(dirpath) / name
                if p.suffix.lower() in inv.MEDIA_EXTENSIONS:
                    media += 1
                    stubs += inv.is_lfs_pointer(p, p.stat().st_size)
    real = media - stubs
    return {"dataset_id": "crema_d", "present": base.is_dir(), "media_files": media, "git_lfs_pointer_stubs": stubs,
            "real_media_files": real, "available": real > 0, "used": False,
            "outcome": "unavailable: every local media file is a Git LFS pointer; nothing trained, nothing "
                       "downloaded" if real == 0 else "real media present but not approved for Task 7"}


# --- build -------------------------------------------------------------------------------------


def _records(root: Path, registry: Mapping[str, Any], stats: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    for dataset_id in DATASETS:
        path, manifest = verify_normalized(root, dataset_id, registry)
        s = stats.setdefault(dataset_id, {"normalised_records": manifest["records"],
                                          "records_sha256": manifest["records_sha256"],
                                          "source_sha256": manifest["source_sha256"],
                                          "source_rows_read": manifest.get("source_rows_read"),
                                          "task5_excluded": manifest.get("excluded", {}),
                                          "unit": manifest.get("unit")})
        used = 0
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    used += 1
                    yield json.loads(line)
        s["normalised_records_used"] = used
        if dataset_id == "hinglish_hate_speech_local_derivative":
            counts: Counter = Counter()
            yield from unlabelled_rows(root, dataset_id, registry, manifest, counts)
            s.update({"unlabelled_rows_used": counts["unlabelled_rows_used"],
                      "blank_unlabelled_rows": counts["blank_unlabelled_row"],
                      "malformed_rows": counts["malformed_row"]})


def _segments(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if record.get("turns"):
        pieces = dialogue_windows(record["turns"])
        return [{"text": text, "labels": sorted({c for i in members
                                                  for c in record["turns"][i].get("source_label_category", [])})}
                for text, members in pieces]
    labels = list(record.get("source_label_category") or [])
    return [{"text": text, "labels": labels} for text in text_windows(str(record.get("text") or ""))]


def build(datasets_root: Path, training: Path, acknowledgement: Optional[str], operator: str = "unspecified",
          registry: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    reg = registry if registry is not None else gov.load_registry()
    basis = authorise(acknowledgement, reg)
    stats: Dict[str, Any] = {}
    records = list(_records(datasets_root, reg, stats))  # ids, keys and text; stays in memory only

    fam = Families()
    by_exact: Dict[str, str] = {}
    for r in records:
        fam.find(r["record_id"])
        if r.get("duplicate_of"):
            fam.union(r["record_id"], r["duplicate_of"])
        key = r.get("exact_key")
        if key:
            if key in by_exact:
                fam.union(r["record_id"], by_exact[key])  # identical text, also across datasets
            else:
                by_exact[key] = r["record_id"]
    family_size = Counter(fam.find(r["record_id"]) for r in records)

    out_dir = corpus_dir(training)
    out_dir.mkdir(parents=True, exist_ok=True)
    partial = out_dir / "segments.jsonl.partial"
    digest = hashlib.sha256()
    window_keys: set = set()
    per: Dict[str, Counter] = {d: Counter() for d in DATASETS}
    languages: Dict[str, Counter] = {d: Counter() for d in DATASETS}
    scripts: Dict[str, Counter] = {d: Counter() for d in DATASETS}
    label_counts: Dict[str, Counter] = {d: Counter() for d in DATASETS}
    with open(partial, "w", encoding="utf-8", newline="\n") as fh:
        for r in records:
            dataset_id = r["dataset_id"]
            family = fam.find(r["record_id"])
            size = family_size[family]
            mlm, aux = partition_of(family)
            windows = _segments(r)
            c = per[dataset_id]
            c["records"] += 1
            c["records_with_text"] += bool(windows)
            c["windows"] += len(windows)
            c["families"] += family == r["record_id"]
            c["duplicate_records"] += size > 1
            languages[dataset_id][r.get("language") or "unknown"] += 1
            scripts[dataset_id][r.get("script") or "none"] += 1
            for k, w in enumerate(windows):
                coverage = k == 0 or dataset_id in ALL_WINDOWS_IN_COVERAGE
                labels = namespaced(dataset_id, w["labels"])
                task = AUX_TASKS.get(dataset_id) if labels else None
                seg = {"schema": CORPUS_SCHEMA, "uid": f"{r['record_id']}#w{k}", "record_id": r["record_id"],
                       "dataset_id": dataset_id, "window": k, "windows": len(windows), "text": w["text"],
                       "language": r.get("language") or "unknown", "script": xc.script_of(w["text"]),
                       "family": family, "family_size": size, "weight": round(1.0 / size, 6),
                       "mlm_partition": mlm, "aux_split": aux, "coverage": coverage,
                       "source_labels": labels, "aux_task": task,
                       "opaque_labels": dataset_id in OPAQUE_LABELS,
                       "artifact_class": xc.ARTIFACT_CLASS, "governance_basis": GOVERNANCE_BASIS}
                line = xc.canonical(seg) + "\n"
                window_keys.add(xc.exact_key(w["text"]))
                digest.update(line.encode("utf-8"))
                fh.write(line)
                c["coverage_windows"] += coverage
                c[f"mlm_{mlm}"] += 1
                c[f"aux_{aux}"] += 1 if task else 0
                for lab in labels:
                    label_counts[dataset_id][lab] += 1
    os.replace(partial, out_dir / "segments.jsonl")
    # Hashed normalised-text keys of every record and window, so the local demo can refuse to be fed
    # an external record verbatim without ever holding or printing the text itself.
    keys = sorted({r["exact_key"] for r in records if r.get("exact_key")} | window_keys)
    keys_tmp = out_dir / "exact_keys.txt.partial"
    keys_tmp.write_text("\n".join(keys) + "\n", encoding="utf-8", newline="\n")
    os.replace(keys_tmp, out_dir / EXACT_KEYS_FILE)

    datasets = {}
    for d in DATASETS:
        s = dict(stats.get(d, {}))
        s.update({k: v for k, v in per[d].items()})
        s["language"] = dict(languages[d])
        s["script"] = dict(scripts[d])
        s["source_label_windows"] = dict(label_counts[d])
        s["aux_task"] = AUX_TASKS.get(d)
        s["labels_opaque"] = d in OPAQUE_LABELS
        s["sensitivity_flags"] = gov.get(reg, d).get("sensitivity_flags", [])
        s["review_status"] = gov.get(reg, d)["review_status"]
        datasets[d] = s
    manifest = {
        "schema": CORPUS_SCHEMA, "schema_version": CORPUS_SCHEMA_VERSION, "corpus": CORPUS_NAME,
        "governance": basis, "artifact_class": xc.ARTIFACT_CLASS,
        "residual_identifier_risk": xc.RESIDUAL_IDENTIFIER_RISK,
        "segments_sha256": digest.hexdigest(), "segments": sum(p["windows"] for p in per.values()),
        "exact_keys": {"file": EXACT_KEYS_FILE, "count": len(keys), "form": "sha256 of the Task 5 comparison form"},
        "window_chars": WINDOW_CHARS, "seed": SEED,
        "partitions": {"mlm_validation_per_mille": MLM_VALIDATION_PER_MILLE,
                       "aux_test_per_mille": AUX_TEST_PER_MILLE, "unit": "duplicate family"},
        "coverage_rule": "every usable record contributes at least its first window to the coverage pass; the "
                         "smaller datasets contribute every window",
        "duplicate_rule": "families join Task 5 exact/near links and identical text across datasets; each window "
                          "is weighted 1/family size",
        "families": len(family_size), "records": len(records),
        "datasets": datasets, "unavailable": [crema_status(datasets_root)],
        "sahay_mapping": "none: source labels stay namespaced; the label firewall is unchanged",
        "note": "Private EXT-119 training artefact. Never commit, print, upload, redistribute or publish.",
    }
    tmp = out_dir / "manifest.json.partial"
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, out_dir / "manifest.json")
    xc.record_override_use(datasets_root, {"event": "ext119_training_corpus_build", "decision": DECISION_ID,
                                           "operator": str(operator)[:80], "segments": manifest["segments"],
                                           "segments_sha256": manifest["segments_sha256"], "at": xc.now()})
    return manifest


def summary(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Counts only: safe to print."""
    rows = {}
    for d, s in manifest["datasets"].items():
        rows[d] = {k: s.get(k) for k in ("normalised_records", "normalised_records_used", "unlabelled_rows_used",
                                         "blank_unlabelled_rows", "records", "windows", "coverage_windows",
                                         "families", "duplicate_records", "mlm_train", "mlm_mlm_validation",
                                         "aux_task", "labels_opaque", "task5_excluded")}
    return {"corpus": manifest["corpus"], "segments": manifest["segments"], "records": manifest["records"],
            "families": manifest["families"], "segments_sha256": manifest["segments_sha256"][:16],
            "datasets": rows, "unavailable": manifest["unavailable"]}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.data.training_corpus", description=__doc__.split("\n")[0])
    parser.add_argument("--root", help=f"overrides {gov.ROOT_ENV}")
    parser.add_argument("--training-root", help=f"overrides {TRAINING_ROOT_ENV}")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument(EXT119_FLAG, dest="ext119", action="store_true", required=True)
    b.add_argument("--acknowledge", required=True)
    b.add_argument("--operator", default="unspecified")
    args = parser.parse_args(argv)
    try:
        root = gov.dataset_root(args.root)
        manifest = build(root, training_root(args.training_root), args.acknowledge, args.operator)
    except (CorpusRefused, xc.AdapterRefused, gov.GovernanceError, gov.DatasetRootError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary(manifest), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
