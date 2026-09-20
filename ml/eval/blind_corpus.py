"""Command line for the blind human-authored evaluation corpus. Stdlib only.

    python -m ml.eval.blind_corpus init            --root R --version v1
    python -m ml.eval.blind_corpus validate-submission FILE --root R
    python -m ml.eval.blind_corpus submit          FILE --actor person-001
    python -m ml.eval.blind_corpus roster-status
    python -m ml.eval.blind_corpus assign          --actor person-001
    python -m ml.eval.blind_corpus export-review   --actor person-001
    python -m ml.eval.blind_corpus import-review   FILE --actor person-001
    python -m ml.eval.blind_corpus export-adjudication SUBMISSION_ID
    python -m ml.eval.blind_corpus adjudicate      FILE --actor person-001
    python -m ml.eval.blind_corpus status
    python -m ml.eval.blind_corpus coverage
    python -m ml.eval.blind_corpus verify-ledgers  [--expect-head NAME=COUNT:SHA]
    python -m ml.eval.blind_corpus freeze          --actor person-001 [--public-manifest PATH]
    python -m ml.eval.blind_corpus verify-frozen
    python -m ml.eval.blind_corpus exit-codes

Every command takes ``--root`` (or reads ``SAHAY_EVAL_ROOT``), ``--version``
(default ``v1``) and ``--json``. All three are parsed BEFORE the subcommand:
``blind_corpus --root R --json status``, not ``blind_corpus status --json``.
A command works only inside the configured root and refuses a path outside it.

Rules these commands keep
  * No command prints scenario text. Status lines and error messages carry
    ids, counts, hashes and reason classes. ``--json`` output is the same data.
  * No command invents human input. Anything that changes state needs
    ``--actor``, which must already be a real person on the roster, and a
    human record file that the tool validates rather than fills.
  * No command mutates the public corpora in ``ml/eval/corpus/``: they are
    opened read-only, to build the leakage index.
  * ``freeze`` refuses unless all fourteen conditions hold, and writes nothing
    when it refuses.
  * The prediction firewall is asserted before any subcommand runs.

Exit codes are listed by ``exit-codes`` and defined in ``blind/exit_codes.py``.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .blind import firewall
from .blind.assignment import staffing, validate_roster
from .blind.exit_codes import (DESCRIPTIONS, EXIT_CONTAMINATION, EXIT_COVERAGE, EXIT_FREEZE_REFUSED,
                               EXIT_LEDGER, EXIT_MISSING_REVIEW, EXIT_OK, EXIT_PRIVACY, EXIT_SCHEMA,
                               EXIT_STATE, EXIT_USAGE)
from .blind.freeze import FreezeError, freeze, preconditions, public_manifest, verify_frozen
from .blind.ledger import LedgerError, head, verify_head
from .blind.paths import ROOT_ENV, RootError
from .blind.plan import PlanError
from .blind.states import StateError
from .blind.store import Store, StoreError, load_record

LEDGERS = ("submissions", "reviews", "adjudications", "states")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _emit(payload: Dict[str, Any], human: str, as_json: bool) -> None:
    """Machine-readable or human-readable. Neither form carries narrative."""
    if as_json:
        print(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True))
    else:
        print(human)


def _store(args: argparse.Namespace) -> Store:
    return Store.open(getattr(args, "root", "") or "", getattr(args, "version", "v1"))


# --- commands -------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    store = _store(args)
    result = store.init()
    _emit(result, f"initialised {store.version} under the configured root: "
                  f"{result['directories']} directories, {len(result['templates'])} blank templates "
                  f"(no scenario, no roster entry)", args.json)
    return EXIT_OK


def cmd_validate_submission(args: argparse.Namespace) -> int:
    store = _store(args)
    report = store.screen(load_record(args.file))
    sid = report["submission_id"]
    if report["schema_errors"]:
        _emit(report, f"{sid}: SCHEMA INVALID, {len(report['schema_errors'])} problem(s)\n  - "
                      + "\n  - ".join(report["schema_errors"]), args.json)
        return EXIT_SCHEMA
    if report["pii"]:
        _emit(report, f"{sid}: possible personal information, {len(report['pii'])} match(es) "
                      f"({', '.join(sorted({h['pattern'] for h in report['pii']}))}); a human must read it",
              args.json)
        return EXIT_PRIVACY
    if report["leakage_severity"]:
        _emit(report, f"{sid}: contamination review required ({report['leakage_severity']}): "
                      + ", ".join(f"{f['check']} vs {f['matched_id']}" for f in report["leakage"]), args.json)
        return EXIT_CONTAMINATION
    _emit(report, f"{sid}: schema valid, no PII match, no overlap with an exposed corpus", args.json)
    return EXIT_OK


def cmd_submit(args: argparse.Namespace) -> int:
    store = _store(args)
    actor = store.actor(args.actor)
    result = store.submit(load_record(args.file), actor, now())
    screen = result["screen"]
    code = EXIT_OK
    if screen["pii"]:
        code = EXIT_PRIVACY
    elif screen["leakage_severity"]:
        code = EXIT_CONTAMINATION
    _emit(result, f"{result['submission_id']}: recorded, state {result['state']} "
                  f"(pii matches {len(screen['pii'])}, leakage {screen['leakage_severity'] or 'none'})",
          args.json)
    return code


def cmd_roster_status(args: argparse.Namespace) -> int:
    store = _store(args)
    roster = store.roster()
    report = staffing(roster)
    errs = validate_roster(roster, store.version)
    if errs:
        _emit({"errors": errs}, "roster invalid:\n  - " + "\n  - ".join(errs), args.json)
        return EXIT_SCHEMA
    human = (f"roster: {report['humans']} human(s), {report['accounts']} account(s); "
             f"authors {len(report['can_author'])}, reviewers {len(report['can_review'])}, "
             f"adjudicators {len(report['can_adjudicate'])}; "
             + ", ".join(f"{lang} reviewers {len(report[f'reviewers_{lang}'])}"
                         for lang in ("en", "hi", "hinglish")))
    _emit(report, human, args.json)
    return EXIT_OK


def cmd_assign(args: argparse.Namespace) -> int:
    store = _store(args)
    actor = store.actor(args.actor)
    allocation = store.save_assignment(actor, now(), args.reviews_per_sample)
    human = (f"assigned {len(allocation['assignments'])} sample(s), "
             f"{allocation['reviews_per_sample']} reviewer(s) each; "
             f"{len(allocation['shortfalls'])} shortfall(s)")
    _emit(allocation, human, args.json)
    return EXIT_OK if allocation["complete"] else EXIT_MISSING_REVIEW


def cmd_export_review(args: argparse.Namespace) -> int:
    store = _store(args)
    store.actor(args.actor)  # a named human is responsible for the export
    written = store.export_packets()
    _emit({"packets": len(written)},
          f"exported {len(written)} blinded packet(s); no system output, no author identity, "
          "no other reviewer's decision", args.json)
    return EXIT_OK


def cmd_import_review(args: argparse.Namespace) -> int:
    store = _store(args)
    actor = store.actor(args.actor)
    result = store.import_review(load_record(args.file), actor, now())
    comparison = result["comparison"]
    human = (f"{result['submission_id']}: review recorded, state {result['state']}, "
             f"{comparison['reviews']} review(s), {len(comparison['conflicts'])} conflict(s)")
    if comparison["copied_reasoning"]:
        human += f"; {len(comparison['copied_reasoning'])} copied-reasoning flag(s) for human inspection"
    _emit(result, human, args.json)
    return EXIT_OK


def cmd_export_adjudication(args: argparse.Namespace) -> int:
    store = _store(args)
    packet = store.adjudication_packet(args.submission_id)
    path = store.path("adjudication", f"{args.submission_id}--packet.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(packet, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    _emit({"submission_id": args.submission_id, "conflicting_fields": packet["conflicting_fields"],
           "critical_conflict": packet["critical_conflict"]},
          f"{args.submission_id}: adjudication packet written; "
          f"{len(packet['conflicting_fields'])} conflicting field(s), "
          f"critical conflict {packet['critical_conflict']}", args.json)
    return EXIT_OK


def cmd_adjudicate(args: argparse.Namespace) -> int:
    store = _store(args)
    actor = store.actor(args.actor)
    result = store.import_adjudication(load_record(args.file), actor, now())
    human = f"{result['submission_id']}: adjudication recorded, state {result['state']}"
    if result["blockers"]:
        human += "; still blocked: " + "; ".join(result["blockers"])
    _emit(result, human, args.json)
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    store = _store(args)
    report = store.status()
    lines = [f"corpus {report['corpus_version']}: {report['submissions']} submission(s), "
             f"{report['reviews']} review(s), {report['adjudications']} adjudication(s), "
             f"{report['eligible']} eligible, frozen {report['frozen']}"]
    for state, count in report["by_state"].items():
        lines.append(f"  {state}: {count}")
    coverage = report["coverage"]
    lines.append(f"  coverage: {coverage.get('samples', 0)} sample(s), "
                 f"{len(coverage.get('shortfalls') or [])} shortfall(s), "
                 f"satisfied {coverage.get('satisfied')}")
    for name, value in report["ledger_heads"].items():
        lines.append(f"  ledger {name}: {value}")
    _emit(report, "\n".join(lines), args.json)
    return EXIT_OK


def cmd_coverage(args: argparse.Namespace) -> int:
    store = _store(args)
    report = store.coverage_report()
    lines = [f"coverage plan {report['plan_version']} for {report['corpus_version']}: "
             f"{report['samples']} of {report['total_min']} sample(s), satisfied {report['satisfied']}"]
    for short in report["shortfalls"][:40]:
        where = f" [{short['language']}]" if short["language"] else ""
        lines.append(f"  {short['kind']} {short['name']}{where}: have {short['have']}, need {short['need']}")
    if len(report["shortfalls"]) > 40:
        lines.append(f"  ... {len(report['shortfalls']) - 40} more shortfall(s)")
    _emit(report, "\n".join(lines), args.json)
    return EXIT_OK if report["satisfied"] else EXIT_COVERAGE


def cmd_verify_ledgers(args: argparse.Namespace) -> int:
    store = _store(args)
    expected: Dict[str, str] = {}
    for item in args.expect_head or []:
        if "=" not in item:
            print("refused: --expect-head takes NAME=COUNT:SHA256")
            return EXIT_USAGE
        name, value = item.split("=", 1)
        if name not in LEDGERS:
            print(f"refused: unknown ledger {name!r}")
            return EXIT_USAGE
        expected[name] = value
    problems: List[str] = []
    heads: Dict[str, str] = {}
    for name in LEDGERS:
        try:
            heads[name] = head(store.ledger(name))
        except LedgerError as exc:
            problems.append(f"{name}: {exc}")
    for name, value in expected.items():
        try:
            verify_head(store.ledger(name), value)
        except LedgerError as exc:
            problems.append(f"{name}: {exc}")
    payload = {"heads": heads, "problems": problems}
    if problems:
        _emit(payload, "ledger verification FAILED:\n  - " + "\n  - ".join(problems), args.json)
        return EXIT_LEDGER
    _emit(payload, "all four ledgers verify; heads " + ", ".join(f"{k}={v}" for k, v in sorted(heads.items())),
          args.json)
    return EXIT_OK


def cmd_freeze(args: argparse.Namespace) -> int:
    store = _store(args)
    actor = store.actor(args.actor)
    if args.dry_run:
        gate = preconditions(store)
        lines = [f"freeze dry run for {store.version}: ok {gate['ok']}, "
                 f"{len(gate['eligible'])} eligible sample(s)"]
        for refusal in gate["refusals"]:
            lines.append(f"  refused: {refusal['condition']} - {refusal['detail']}")
        _emit(gate, "\n".join(lines), args.json)
        return EXIT_OK if gate["ok"] else EXIT_FREEZE_REFUSED
    result = freeze(store, actor, now())
    manifest = result["manifest"]
    if args.public_manifest:
        target = Path(args.public_manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(public_manifest(manifest), indent=1, ensure_ascii=False,
                                     sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    _emit({"samples": result["samples"], "corpus_sha256": manifest["corpus_sha256"],
           "ledger_heads": manifest["ledger_heads"], "files": result["files"]},
          f"froze {result['samples']} sample(s) as {store.version}; corpus sha256 "
          f"{manifest['corpus_sha256']}", args.json)
    return EXIT_OK


def cmd_verify_frozen(args: argparse.Namespace) -> int:
    store = _store(args)
    problems = verify_frozen(store)
    if problems:
        _emit({"problems": problems}, "frozen corpus FAILED verification:\n  - " + "\n  - ".join(problems),
              args.json)
        return EXIT_LEDGER
    manifest = store.frozen_manifest()
    _emit({"corpus_version": manifest["corpus_version"], "samples": manifest["samples"],
           "corpus_sha256": manifest["corpus_sha256"]},
          f"frozen corpus {manifest['corpus_version']} verifies: {manifest['samples']} sample(s), "
          f"sha256 {manifest['corpus_sha256']}", args.json)
    return EXIT_OK


def cmd_exit_codes(args: argparse.Namespace) -> int:
    payload = {str(code): text for code, text in sorted(DESCRIPTIONS.items())}
    _emit(payload, "\n".join(f"{code:>3}  {text}" for code, text in sorted(DESCRIPTIONS.items())), args.json)
    return EXIT_OK


# --- parser ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ml.eval.blind_corpus",
                                     description="Blind human-authored evaluation corpus tooling. "
                                                 "Never authors a sample and never fills a human record.")
    parser.add_argument("--root", default="", help=f"private evaluation root (default: ${ROOT_ENV})")
    parser.add_argument("--version", default="v1", help="corpus version, e.g. v1")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the private layout and blank templates").set_defaults(fn=cmd_init)

    p = sub.add_parser("validate-submission", help="check one author submission; records nothing")
    p.add_argument("file")
    p.set_defaults(fn=cmd_validate_submission)

    p = sub.add_parser("submit", help="record one validated human submission")
    p.add_argument("file")
    p.add_argument("--actor", required=True, help="roster person_id responsible for this action")
    p.set_defaults(fn=cmd_submit)

    sub.add_parser("roster-status", help="who the roster can staff").set_defaults(fn=cmd_roster_status)

    p = sub.add_parser("assign", help="deterministically allocate reviewers")
    p.add_argument("--actor", required=True)
    p.add_argument("--reviews-per-sample", type=int, default=2)
    p.set_defaults(fn=cmd_assign)

    p = sub.add_parser("export-review", help="write one blinded packet per assigned reviewer")
    p.add_argument("--actor", required=True)
    p.set_defaults(fn=cmd_export_review)

    p = sub.add_parser("import-review", help="append one human review record")
    p.add_argument("file")
    p.add_argument("--actor", required=True)
    p.set_defaults(fn=cmd_import_review)

    p = sub.add_parser("export-adjudication", help="write the adjudication packet for one conflict")
    p.add_argument("submission_id")
    p.set_defaults(fn=cmd_export_adjudication)

    p = sub.add_parser("adjudicate", help="append one human adjudication record")
    p.add_argument("file")
    p.add_argument("--actor", required=True)
    p.set_defaults(fn=cmd_adjudicate)

    sub.add_parser("status", help="states, counts, coverage and ledger heads").set_defaults(fn=cmd_status)
    sub.add_parser("coverage", help="coverage against the plan").set_defaults(fn=cmd_coverage)

    p = sub.add_parser("verify-ledgers", help="verify the four hash chains")
    p.add_argument("--expect-head", action="append", metavar="NAME=COUNT:SHA256")
    p.set_defaults(fn=cmd_verify_ledgers)

    p = sub.add_parser("freeze", help="freeze the corpus if every condition holds")
    p.add_argument("--actor", required=True)
    p.add_argument("--dry-run", action="store_true", help="report the gate without writing anything")
    p.add_argument("--public-manifest", default="", help="also write the content-free manifest to this path")
    p.set_defaults(fn=cmd_freeze)

    sub.add_parser("verify-frozen", help="re-verify a frozen corpus").set_defaults(fn=cmd_verify_frozen)
    sub.add_parser("exit-codes", help="print the documented exit codes").set_defaults(fn=cmd_exit_codes)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except StoreError as exc:
        print(f"refused: {exc}")
        return exc.code
    except FreezeError as exc:
        print(f"refused: {exc}")
        return EXIT_FREEZE_REFUSED
    except LedgerError as exc:
        print(f"refused: {exc}")
        return EXIT_LEDGER
    except StateError as exc:
        print(f"refused: {exc}")
        return EXIT_STATE
    except (RootError, PlanError) as exc:
        print(f"refused: {exc}")
        return EXIT_USAGE


if __name__ == "__main__":
    firewall.assert_clean("blind_corpus")
    sys.exit(main())
