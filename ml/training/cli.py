"""Task 7 training commands. Every command runs offline with sockets actively blocked.

    python -m ml.training.cli preflight
    python -m ml.training.cli fictional
    python -m ml.training.cli stage-a [--limit N]
    python -m ml.training.cli stage-b [--limit N]
    python -m ml.training.cli stage-c [--seeds 13 42 97] [--limit N]
    python -m ml.training.cli regression
    python -m ml.training.cli verify-shadow
    python -m ml.training.cli error-analysis
    python -m ml.training.cli hardening-build
    python -m ml.training.cli hardening-verify
    python -m ml.training.cli stage-c7b-plan
    python -m ml.training.cli stage-c7b --phase 1|2
    python -m ml.training.cli stage-c7b-select
    python -m ml.training.cli stage-c7b-evaluate
    python -m ml.training.cli task7b-retention
    python -m ml.training.cli stage-c7b-correct

Needs ``SAHAY_TRAINING_ROOT`` (private outputs) and ``SAHAY_MODELS_ROOT`` (pinned MuRIL); neither has
a default. Output is aggregate only: no text, no transcript, no absolute path. Reports and
checkpoints stay beneath ``SAHAY_TRAINING_ROOT``.
"""

import argparse
import importlib
import json
import sys
from typing import Any, Dict, List, Optional

from ..runtime import config as rc
from ..runtime.offline import network_blocked
from . import fictional, paths


def preflight(root_arg: Optional[str], models_arg: Optional[str]) -> Dict[str, Any]:
    root = paths.training_root(root_arg)
    manifest = rc.load_manifest()
    entry = rc.get_model(manifest, "muril_base_cased")
    muril = rc.verify_files(rc.model_dir(rc.models_root(models_arg), entry), entry["files"], full_hash=True)
    corpus_dir = paths.confined(root, *paths.EXTERNAL_CORPUS.split("/"))
    cm = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))
    corpus_ok = paths.sha256_file(corpus_dir / "segments.jsonl") == cm["segments_sha256"]
    from . import torchkit as tk
    t = tk.torch()
    info: Dict[str, Any] = {"muril_revision": entry["revision"], "muril_integrity_ok": muril["ok"],
                            "external_corpus_hash_ok": corpus_ok, "external_segments": cm["segments"],
                            "cuda": t.cuda.is_available()}
    if t.cuda.is_available():
        free, total = t.cuda.mem_get_info()
        info.update({"gpu": t.cuda.get_device_name(0), "vram_free_mib": round(free / 2**20),
                     "vram_total_mib": round(total / 2**20), "gpu_temperature_c": tk.gpu_temperature()})
    psutil = importlib.import_module("psutil")
    info["disk_free_gib"] = round(psutil.disk_usage(str(root)).free / 2**30, 1)
    info["ok"] = bool(muril["ok"] and corpus_ok)
    return info


def verify_shadow(root_arg: Optional[str]) -> Dict[str, Any]:
    """Selected checkpoint: hashes against its training record, offline reload, repeat determinism."""
    from ..shadow.classifier import ShadowClassifier
    root = paths.training_root(root_arg)
    pointer = json.loads(paths.confined(root, "checkpoints", "stage-c", "SELECTED.json").read_text(encoding="utf-8"))
    report = json.loads(paths.confined(root, "reports", "stage-c", f"{pointer['run']}.json").read_text(encoding="utf-8"))
    recorded = next(s for s in report["seeds"] if s["seed"] == pointer["seed"])["files_sha256"]
    directory = paths.confined(root, *pointer["checkpoint"].split("/"))
    mismatched = [name for name, digest in recorded.items()
                  if paths.sha256_file(paths.confined(directory, *name.split("/"))) != digest]
    records = [r for r in fictional.load(root) if r["split"] == "synthetic_development_test"][:200]
    shadow = ShadowClassifier(str(root))
    state = shadow.load()
    first = [shadow.classify(r["turns"]).probabilities for r in records]
    second = [shadow.classify(r["turns"]).probabilities for r in records]
    shadow.unload()
    return {"selected": {k: pointer[k] for k in ("run", "seed")}, "files_checked": len(recorded),
            "hash_mismatches": mismatched, "load_status": state.status, "device": state.device,
            "repeat_records": len(records), "repeat_identical": first == second and all(p is not None for p in first)}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.training.cli", description=__doc__.split("\n")[0])
    parser.add_argument("--training-root", help=f"overrides {paths.TRAINING_ROOT_ENV}")
    parser.add_argument("--models-root", help=f"overrides {rc.ROOT_ENV}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    sub.add_parser("fictional")
    for name in ("stage-a", "stage-b", "stage-c"):
        p = sub.add_parser(name)
        p.add_argument("--limit", type=int, default=None, help="smoke run on a small slice only")
        if name == "stage-c":
            p.add_argument("--seeds", type=int, nargs="+", default=[13, 42, 97])
            p.add_argument("--epochs", type=int, default=6, help="maximum epochs; early stopping decides")
            p.add_argument("--patience", type=int, default=2)
            p.add_argument("--tag", default="run1", help="alphanumeric run tag")
    sub.add_parser("regression")
    sub.add_parser("verify-shadow")
    sub.add_parser("error-analysis")
    sub.add_parser("hardening-build")
    sub.add_parser("hardening-verify")
    sub.add_parser("stage-c7b-plan")
    p7 = sub.add_parser("stage-c7b")
    p7.add_argument("--phase", type=int, choices=(1, 2), required=True)
    sub.add_parser("stage-c7b-select")
    sub.add_parser("stage-c7b-evaluate")
    sub.add_parser("task7b-retention")
    sub.add_parser("stage-c7b-correct")
    args = parser.parse_args(argv)
    try:
        with network_blocked() as net:
            if args.command == "preflight":
                payload = preflight(args.training_root, args.models_root)
            elif args.command == "fictional":
                m = fictional.build(paths.training_root(args.training_root))
                payload = {k: m[k] for k in ("records", "records_sha256", "templates", "blocked", "splits")}
            elif args.command == "stage-a":
                from . import stage_a
                r = stage_a.run(paths.training_root(args.training_root), args.models_root, limit=args.limit)
                payload = {k: r.get(k) for k in ("status", "run_id", "optimizer_steps", "validation_before",
                                                 "validation_after_coverage", "validation_after_continuation",
                                                 "coverage", "continuation", "resources", "checkpoint")}
            elif args.command == "stage-b":
                from . import stage_b
                payload = stage_b.run(paths.training_root(args.training_root), limit=args.limit)
            elif args.command == "stage-c":
                from . import stage_c
                payload = stage_c.run(paths.training_root(args.training_root), seeds=tuple(args.seeds),
                                      limit=args.limit, epochs=args.epochs, patience=args.patience, tag=args.tag)
            elif args.command == "hardening-build":
                from . import hardening
                root = paths.training_root(args.training_root)
                keys_path = paths.confined(root, *paths.EXTERNAL_CORPUS.split("/"), "exact_keys.txt")
                keys = set(keys_path.read_text(encoding="utf-8").split()) if keys_path.is_file() else None
                r = hardening.build(root, keys)
                payload = {k: r[k] for k in ("generated", "kept", "contamination", "families", "review_packet")}
                payload["freeze"] = {k: r["freeze"][k] for k in ("version", "frozen_at", "records", "state")}
            elif args.command in ("stage-c7b-plan", "stage-c7b", "stage-c7b-select", "stage-c7b-evaluate",
                                  "task7b-retention", "stage-c7b-correct"):
                from . import stage_c7b
                root = paths.training_root(args.training_root)
                if args.command == "stage-c7b-plan":
                    payload = stage_c7b.write_plan(root)
                elif args.command == "stage-c7b":
                    payload = stage_c7b.run_phase(root, args.phase)
                elif args.command == "stage-c7b-select":
                    payload = stage_c7b.select(root)
                elif args.command == "task7b-retention":
                    payload = stage_c7b.retention_proposal(root)
                elif args.command == "stage-c7b-correct":
                    payload = stage_c7b.correct_holdout_report(root)
                else:
                    payload = stage_c7b.evaluate(root)
            elif args.command == "hardening-verify":
                from . import hardening
                payload = hardening.verify_freeze(paths.training_root(args.training_root))
            elif args.command == "error-analysis":
                from . import error_analysis
                payload = error_analysis.run(paths.training_root(args.training_root))
            elif args.command == "verify-shadow":
                payload = verify_shadow(args.training_root)
            else:
                from . import regression
                payload = regression.run(paths.training_root(args.training_root))
        payload["network_attempts_blocked"] = net["attempts"]
    except (paths.TrainingRootError, rc.RuntimeConfigError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
