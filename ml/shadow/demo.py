"""Local ML-owned demonstration: deterministic pipeline (authoritative) beside the shadow classifier.

    python -m ml.shadow.demo examples
    python -m ml.shadow.demo text --example 3
    python -m ml.shadow.demo --checkpoint-set task7b text --example 3
    python -m ml.shadow.demo text --language hinglish --text "<fictional sentence>" [--text "<next turn>"]
    python -m ml.shadow.demo voice --synthetic silence|speechlike --language hi
    python -m ml.shadow.demo voice --audio <private consented 16 kHz mono WAV> --language hi

This is an operator-run CLI, not a product: no server, no listener, no upload, no database write,
no file written. Inputs and transcripts are processed in memory and never printed or logged.
Typed text is refused if it reproduces a record of the EXT-119 external corpus (checked against
private hashed keys, never against text). Voice input goes only through ``GatedTranscriber``:
Silero VAD first, validated intervals, and Whisper skipped when no speech is found.

The deterministic crisis pre-check, detectors, band and routing are printed as the authority. The
shadow output is printed separately as experimental: it cannot change any of them, and no
external source label, SVI, D4 value, diagnosis or "safe" verdict is ever shown for it.
"""

import argparse
import hashlib
import json
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..assessment import assess
from ..eval.blind import normalize as nz
from ..eval.predict import NOT_IMPLEMENTED, predict
from ..runtime.offline import network_blocked
from ..training import paths
from . import model as sm
from .classifier import ShadowClassifier

BANNER = ("LOCAL ML DEMONSTRATION (EXT-119): operator-only, not a product, not victim-facing. The deterministic "
          "pipeline is authoritative; the shadow model is experimental and cannot change it.")
EXACT_KEYS = ("corpora", "external-ext119-v1", "exact_keys.txt")

#: Built-in fictional demonstration inputs, written for this file only.
EXAMPLES: List[Dict[str, Any]] = [
    {"language": "en", "turns": ["Hello, I have a question about a form I need to fill."]},
    {"language": "en", "turns": ["Some men are standing outside our gate right now and shouting at us.",
                                 "I am scared to open the door."]},
    {"language": "hinglish", "turns": ["Thane wale meri shikayat likh hi nahi rahe, teen baar ja chuki hoon."]},
    {"language": "hi", "turns": ["गाँव वालों ने हमारा पानी भरना बंद करवा दिया है।", "कोई दुकानदार सामान नहीं देता।"]},
    {"language": "en", "turns": ["I feel so hopeless that I do not want to wake up tomorrow."]},
    {"language": "hinglish", "turns": ["Mujhe kisi insaan se baat karni hai, abhi.",
                                       "Ghar pe koi mera phone dekhta rehta hai."]},
    {"language": "en", "turns": ["My uncle fell from the roof and is not responding, there is blood."]},
    {"language": "hi", "turns": ["मैं ठीक हूँ, बस योजना के बारे में जानकारी चाहिए थी।"]},
]


class DemoRefused(Exception):
    pass


def external_guard(training_root: Optional[str]) -> set:
    """Hashed comparison-form keys of every external record and window, or refuse typed input."""
    try:
        root = paths.training_root(training_root)
        path = paths.confined(root, *EXACT_KEYS)
    except paths.TrainingRootError as exc:
        raise DemoRefused(f"typed input needs the external-record guard, which is unavailable: {exc}") from None
    if not path.is_file():
        raise DemoRefused("typed input needs the external-record guard; its key file is missing")
    return set(path.read_text(encoding="utf-8").split())


def reproduces_external(texts: Sequence[str], keys: set) -> bool:
    joined = " ".join(texts)
    return any(hashlib.sha256(nz.compare(t).encode("utf-8")).hexdigest() in keys for t in (*texts, joined))


def deterministic(turns: Sequence[Mapping[str, Any]], channel: str) -> Dict[str, Any]:
    sample = {"id": "DEMO-LOCAL", "channel": channel, "turns": [dict(t) for t in turns]}
    p = predict(sample)
    a = assess(sample["turns"], True, p["crisis_precheck"], channel=channel)
    d4 = a["dims"].get("D4", {})
    return {"crisis_precheck": p["crisis_precheck"], "routed_critical": p["routed_critical"], "band": a["band"],
            "needs_human": a["needs_human"],
            "detectors": {c: v["predicted"] for c, v in p["categories"].items()},
            "d4": "unavailable (" + str(d4.get("basis") or "not measured") + ")"}


def side_by_side(turns: Sequence[Mapping[str, Any]], channel: str, shadow: ShadowClassifier) -> Dict[str, Any]:
    det = deterministic(turns, channel)  # computed first and independently of the model
    try:
        sh = shadow.classify(turns).as_dict()
    except Exception as exc:  # belt and braces: a model problem never touches the authority
        sh = {"model_id": sm.MODEL_ID, "status": "failed", "reason": type(exc).__name__, "probabilities": None,
              "development_firings": None}
    disagreements = {}
    if sh.get("development_firings"):
        for c, fired in sh["development_firings"].items():
            d = det["detectors"].get(c)
            disagreements[c] = ("no deterministic text detector" if d is None else
                                ("disagrees" if bool(d) != bool(fired) else "agrees"))
    return {"authoritative_deterministic": det, "experimental_shadow": sh, "shadow_vs_deterministic": disagreements}


def product_line(sh: Mapping[str, Any]) -> str:
    """Never an approval: failing any gate shows the fixed rejection line."""
    if sh.get("deployment_status") == "candidate_for_human_review" and sh.get("promotion_gates_passed"):
        return "Candidate for human review only; not approved for product integration"
    return "Not approved for product integration"


def render(result: Mapping[str, Any], meta: Mapping[str, Any]) -> str:
    det, sh = result["authoritative_deterministic"], result["experimental_shadow"]
    lines = [BANNER, "", f"Input: {meta['summary']} (text is never echoed)", "",
             "AUTHORITATIVE deterministic pipeline",
             f"  crisis pre-check fired : {det['crisis_precheck']}",
             f"  routed Critical        : {det['routed_critical']}",
             f"  band                   : {det['band'] if det['band'] else 'none (Needs Human Assessment)'}",
             f"  D4                     : {det['d4']}"]
    for c, v in det["detectors"].items():
        lines.append(f"  {c:32s}: {'no text detector (' + NOT_IMPLEMENTED[c] + ')' if v is None else v}")
    lines += ["", f"EXPERIMENTAL SHADOW OUTPUT ({sm.MODEL_ID}; uncalibrated; development threshold "
                  f"{sm.THRESHOLD}; cannot change anything above)", f"  status: {sh['status']}"
              + (f" ({sh.get('reason')})" if sh.get("reason") else "")]
    lines += [f"  checkpoint set          : {sh.get('checkpoint_set', 'task7')} "
              f"(sha256 {str(sh.get('checkpoint_sha256') or 'n/a')[:16]})",
              f"  checkpoint status       : {sh.get('deployment_status', 'rejected_for_product_integration')}",
              f"  promotion gates passed  : {sh.get('promotion_gates_passed')}",
              f"  promotion fully evaluable: {sh.get('promotion_metrics_fully_evaluable')}",
              f"  product integration     : {product_line(sh)}"]
    if sh.get("probabilities"):
        for c, prob in sh["probabilities"].items():
            flag = result["shadow_vs_deterministic"].get(c, "")
            lines.append(f"  {c:32s}: p={prob:.3f} development firing={sh['development_firings'][c]}  [{flag}]")
    lines += ["", f"Runtime: {meta.get('runtime', 'text mode')}; network attempts blocked: {meta.get('network_attempts_blocked')}"]
    return "\n".join(lines)


def run_text(args: argparse.Namespace, shadow: ShadowClassifier) -> Dict[str, Any]:
    if args.example is not None:
        if not 0 <= args.example < len(EXAMPLES):
            raise DemoRefused(f"--example must be 0..{len(EXAMPLES) - 1}")
        ex = EXAMPLES[args.example]
        texts, language = ex["turns"], ex["language"]
    else:
        texts = [t for t in (args.text or []) if t and t.strip()]
        if not texts:
            raise DemoRefused("give --example N or at least one --text")
        if reproduces_external(texts, external_guard(args.training_root)):
            raise DemoRefused("this input reproduces an external training record; demo inputs must be fictional")
        language = args.language
    turns = [{"id": f"t{i + 1}", "speaker": "victim", "text": t, "state": "S2"} for i, t in enumerate(texts)]
    result = side_by_side(turns, "mobile_chat", shadow)
    return {"result": result, "meta": {"summary": f"{len(turns)} victim turn(s), language {language}, "
                                                  f"{sum(len(t) for t in texts)} characters"}}


def run_voice(args: argparse.Namespace, shadow: ShadowClassifier) -> Dict[str, Any]:
    from ..runtime import audio as au
    from ..runtime.asr import WhisperASR
    from ..runtime.pipeline import GatedTranscriber
    from ..runtime.vad import SileroVAD
    if args.audio:
        from ..runtime.verify_models import read_private_wav
        samples, source = read_private_wav(args.audio), "private recording (path not shown)"
    else:
        samples = (au.silence(6) if args.synthetic == "silence" else
                   au.concat(au.silence(1.5), au.voiced_pattern(3), au.silence(1.5)))
        source = f"generated {args.synthetic} signal (not speech)"
    gated = GatedTranscriber(SileroVAD(), WhisperASR())
    try:
        asr = gated.transcribe(samples, args.language)
    finally:
        del samples
        gated.unload()
    runtime = (f"VAD intervals {asr.intervals_detected}, Whisper invoked {asr.decoder_invoked}, "
               f"vad_gated {asr.vad_gated}, transcript {len(asr.text)} characters (processed in memory, not shown)")
    if not asr.decoder_invoked or not asr.text:
        return {"result": None, "meta": {"summary": f"{source}: no speech detected, Whisper skipped, nothing to assess"
                                         if not asr.decoder_invoked else f"{source}: no transcript text",
                                         "runtime": runtime}}
    turns = [{"id": "t1", "speaker": "victim", "text": asr.text, "state": "S2"}]
    result = side_by_side(turns, "mobile_voice", shadow)
    del turns
    return {"result": result, "meta": {"summary": f"{source}, language {args.language}", "runtime": runtime}}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.shadow.demo", description=__doc__.split("\n")[0])
    parser.add_argument("--training-root", help=f"overrides {paths.TRAINING_ROOT_ENV}")
    parser.add_argument("--json", action="store_true", help="print the aggregate result as JSON")
    parser.add_argument("--checkpoint-set", choices=("task7", "task7b"), default="task7",
                        help="which private shadow checkpoint to load (explicit; default task7)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("examples")
    t = sub.add_parser("text")
    t.add_argument("--example", type=int)
    t.add_argument("--text", action="append")
    t.add_argument("--language", choices=("en", "hi", "hinglish"), default="en")
    v = sub.add_parser("voice")
    group = v.add_mutually_exclusive_group(required=True)
    group.add_argument("--synthetic", choices=("silence", "speechlike"))
    group.add_argument("--audio")
    v.add_argument("--language", choices=("hi", "en"), required=True)
    args = parser.parse_args(argv)
    if args.command == "examples":
        for i, ex in enumerate(EXAMPLES):
            print(f"{i}: {ex['language']}, {len(ex['turns'])} turn(s) (fictional)")
        return 0
    shadow = ShadowClassifier(args.training_root, checkpoint_set=args.checkpoint_set)
    try:
        with network_blocked() as net:  # the demonstration is offline: any connection attempt is refused
            out = run_text(args, shadow) if args.command == "text" else run_voice(args, shadow)
        out["meta"]["network_attempts_blocked"] = net["attempts"]
    except DemoRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    finally:
        shadow.unload()
    if args.json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    elif out["result"] is None:
        print(BANNER + "\n\n" + out["meta"]["summary"] + "\nRuntime: " + out["meta"]["runtime"])
    else:
        print(render(out["result"], out["meta"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
