"""Reproducibility and independence checks for the evaluation. Stdlib only.

  determinism        the whole evaluation, run twice, yields identical output
  scenario_replay    replaying a conversation turn by turn (as the backend's
                     assessment worker does) gives the same result twice, and
                     the last cycle equals a one-shot assessment
  llm_off            the dialogue walks from opening to closing with no LLM:
                     every rephrasable intent has a pre-written fallback in
                     both languages that passes the validator; fixed scripts
                     fail closed until approved
  offline            the evaluation completes with networking disabled, no
                     LLM credentials in the environment, and no model, audio
                     or deep-learning package imported
"""

import contextlib
import hashlib
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Sequence

from ..assessment import assess
from ..dialogue import intents, next_turn
from ..dialogue.states import STATE_SLOTS, parse
from ..guardrails import crisis_check, validate

#: Packages that must never be imported on the default evaluation path.
FORBIDDEN_MODULES = (
    "torch", "transformers", "faster_whisper", "ctranslate2", "silero", "sounddevice", "soundfile",
    "librosa", "numpy", "openai", "anthropic", "requests", "httpx", "urllib3", "tensorflow", "onnxruntime",
)
#: Environment variables an LLM provider would read.
LLM_ENV = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
           "LLM_PROVIDER", "HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def determinism(fn: Callable[[], Any], runs: int = 2) -> Dict[str, Any]:
    hashes = [canonical_hash(fn()) for _ in range(runs)]
    return {"runs": runs, "identical": len(set(hashes)) == 1, "sha256": hashes[0]}


def scenario_replay(samples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Incremental replay (one cycle per victim turn) for multi-turn samples."""
    checked, inconsistent = 0, []
    for s in samples:
        if len([t for t in s["turns"] if t["speaker"] == "victim"]) < 2:
            continue
        checked += 1
        turns = [dict(t) for t in s["turns"]]

        def replay():
            cycles, crisis = [], False
            for i in range(1, len(turns) + 1):
                prefix = turns[:i]
                crisis = crisis or crisis_check(prefix[-1]["text"])["crisis"]
                r = assess(prefix, True, crisis, channel=s["channel"])
                cycles.append({"band": r["band"], "svi": r["svi"], "alerts": r["alerts"],
                               "overrides": r["overrides_applied"], "abstain": r["abstention_reasons"]})
            return cycles, crisis

        first, crisis = replay()
        second, _ = replay()
        one_shot = assess(turns, True, crisis, channel=s["channel"])
        final = {"band": one_shot["band"], "svi": one_shot["svi"], "alerts": one_shot["alerts"],
                 "overrides": one_shot["overrides_applied"], "abstain": one_shot["abstention_reasons"]}
        if first != second or first[-1] != final:
            inconsistent.append(s["id"])
    return {"multi_turn_samples": checked, "inconsistent": inconsistent, "consistent": not inconsistent}


def llm_off() -> Dict[str, Any]:
    """Walk the state machine end to end with no LLM and check every fallback."""
    problems: List[str] = []
    fallbacks = 0
    for intent in sorted(intents.REPHRASABLE_INTENTS):
        for lang in intents.SUPPORTED_LANGS:
            text = intents.fallback_text(intent, lang)
            if not text:
                problems.append(f"{intent}/{lang}: no fallback")
                continue
            fallbacks += 1
            r = validate(text, intent, lang)
            if not r["ok"]:
                problems.append(f"{intent}/{lang}: fallback rejected by the validator ({r['reason']})")

    walks = {}
    for lang in intents.SUPPORTED_LANGS:
        state, slots, path = None, {"_sources": {}}, []
        for _ in range(20):
            step = next_turn(state, slots, None, {"lang": lang})
            path.append(step["next_state"])
            if step["fixed_script"] and not step["script_available"]:
                path[-1] += "(fixed script unavailable: fail closed)"
            current = parse(step["next_state"])
            for name in STATE_SLOTS.get(current, ()):
                slots[name] = "answered"
                slots["_sources"][name] = "answered"
            if step["next_state"] == "S9" or step["next_state"] in ("SX", "SH"):
                break
            state = step["next_state"]
        walks[lang] = path
        if not path or not path[-1].startswith("S9"):
            problems.append(f"{lang}: dialogue did not reach S9 without an LLM")
    return {"rephrasable_fallbacks_checked": fallbacks, "walks": walks, "problems": problems,
            "completed": not problems,
            "fixed_scripts_note": "S0/S9/SX/SH are unapproved and fail closed; this is expected, not an LLM gap"}


class NetworkBlocked(RuntimeError):
    pass


@contextlib.contextmanager
def offline() -> Iterator[Dict[str, Any]]:
    """Disable networking, hide LLM credentials, and record forbidden imports."""
    saved_env = {k: os.environ.pop(k) for k in LLM_ENV if k in os.environ}
    originals = (socket.socket, socket.create_connection, socket.getaddrinfo)
    attempts: List[str] = []

    def _blocked(*args, **kwargs):
        attempts.append(repr(args[:2]))
        raise NetworkBlocked("network access attempted during offline evaluation")

    socket.socket = _blocked  # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    socket.getaddrinfo = _blocked  # type: ignore[assignment]
    before = set(sys.modules)
    report: Dict[str, Any] = {"network_attempts": attempts}
    try:
        yield report
    finally:
        socket.socket, socket.create_connection, socket.getaddrinfo = originals
        os.environ.update(saved_env)
        new = set(sys.modules) - before
        report["forbidden_modules_loaded"] = sorted(
            m for m in set(sys.modules) if m.split(".")[0] in FORBIDDEN_MODULES)
        report["new_modules_during_run"] = len(new)
        report["llm_env_hidden"] = sorted(saved_env)
        report["ok"] = not attempts and not report["forbidden_modules_loaded"]


#: Names that identify the externally downloaded datasets, which the ML path
#: must never open, extract or read (safety-hardening phase rule).
EXTERNAL_CORPUS_MARKERS = ("datasets/", "dreaddit", "emoinhindi", "common_voice", "ravdess", "crema", ".zip")


@contextlib.contextmanager
def file_access_log() -> Iterator[List[str]]:
    """Record every path opened through builtins.open / io.open while active."""
    import builtins
    import io as _io

    opened: List[str] = []
    original_open, original_io_open = builtins.open, _io.open

    def _logging_open(file, *args, **kwargs):
        opened.append(str(file))
        return original_open(file, *args, **kwargs)

    builtins.open = _logging_open  # type: ignore[assignment]
    _io.open = _logging_open  # type: ignore[assignment]
    try:
        yield opened
    finally:
        builtins.open, _io.open = original_open, original_io_open


def external_corpus_access(opened: List[str]) -> List[str]:
    """Opened paths that look like an external corpus (must always be empty)."""
    return [p for p in opened
            if any(m in p.replace("\\", "/").casefold() for m in EXTERNAL_CORPUS_MARKERS)]


def static_imports(root: Path) -> Dict[str, Any]:
    """No ML source file on the default path imports a forbidden package."""
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if "tests" in path.parts or ".venv" in path.parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                mod = stripped.split()[1].split(".")[0]
                if mod in FORBIDDEN_MODULES:
                    offenders.append(f"{path.relative_to(root.parent).as_posix()}: {stripped}")
    return {"offenders": offenders, "ok": not offenders}
