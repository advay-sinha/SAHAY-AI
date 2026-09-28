"""M2 turn-latency benchmark: voice turns through the real upload endpoint, timed per stage.

    # 1. once: render the fictional utterances (Windows voices, nothing downloaded)
    pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\\make-benchmark-audio.ps1
    # 2. in another window: the loopback speech-to-text process (sahay-ml-models environment)
    python -m ml.voice.service
    # 3. the benchmark (backend environment)
    backend\\.venv\\Scripts\\python.exe backend\\scenarios\\latency_benchmark.py --rounds 2

Each round opens one ``mobile_voice`` session per voice and uploads that voice's utterances in
order to ``POST /sessions/{id}/audio`` in-process (FastAPI TestClient), so the backend, intake,
dialogue policy, crisis pre-check and assessment scheduling all run as in the demo. It uses a
disposable SQLite file under runtime/db (APP_ENV=test) and never touches the development
database. ``--asr mock`` skips the speech process to time the backend alone.

It reports per-stage p50 / p95 / max from ``latency_metrics`` plus the client-observed request
time. Stages the server cannot see are listed, never invented:
- VAD endpointing happens on the phone (700 ms of silence, configured, not measured here);
- upload time over the LAN needs the phone;
- the first TTS chunk waits for M13.

The first request per voice is a warm-up and is excluded. The word error rate on this synthetic
speech is a sanity check only, never M6. Output (aggregates only) goes to runtime/eval/.
"""

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Sequence

REPO = Path(__file__).resolve().parents[2]
RUNTIME_DB = (REPO / "runtime" / "db").resolve()
AUDIO_DIR = REPO / "runtime" / "bench-audio"
OUT_DIR = REPO / "runtime" / "eval"
BUDGET_MS = {"vad_endpoint": 700, "asr_final": 600, "safety_precheck": 50, "dialogue_policy": 10,
             "llm_phrasing": 800, "output_validator": 20, "tts_first_chunk": 500, "total": 3000}
NOT_MEASURED = {
    "vad_endpoint": "on the phone: 700 ms of trailing silence (configured, not measured here)",
    "lan_upload": "phone to laptop over Wi-Fi: needs the phone",
    "tts_on_the_phone": "download and playback start on the phone: needs the phone",
}
#: Fictional reply-style sentences for timing the offline voice (no assistant turn is spoken yet:
#: intent text still awaits language review). Measured with --tts windows_voice.
TTS_SENTENCES = (
    "Thank you for telling me. You can stop at any time.",
    "Can you tell me when this happened?",
    "Are you somewhere safe right now?",
    "Is anyone hurt and in need of a doctor?",
    "Have you been able to speak to the police about this?",
    "I am sharing this with a person who can help.",
)


def prepare(db_path: Path, asr: str, service_url: str) -> None:
    if not str(db_path).startswith(str(RUNTIME_DB)):
        raise SystemExit(f"refusing: {db_path} is outside {RUNTIME_DB}")
    os.environ.update({"DATABASE_URL": f"sqlite+aiosqlite:///{db_path.as_posix()}", "APP_ENV": "test",
                       "ASR_PROVIDER": asr, "ASR_SERVICE_URL": service_url, "LLM_PROVIDER": "mock"})
    os.environ.setdefault("SEED_PASSWORD", "latency-local-only-" + uuid.uuid4().hex[:8])
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=str(REPO / "backend"),
                       env=os.environ.copy(), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("alembic upgrade failed:\n" + r.stderr[-2000:])


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(q / 100 * len(ordered) + 0.5)) - 1))
    return round(ordered[k], 1)


def summarise(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "p50": percentile(values, 50), "p95": percentile(values, 95),
            "max": round(max(values), 1), "mean": round(statistics.fmean(values), 1)}


def wer(reference: str, hypothesis: str) -> float:
    ref = re.findall(r"[a-z']+", reference.lower())
    hyp = re.findall(r"[a-z']+", hypothesis.lower())
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[len(hyp)] / max(1, len(ref))


def run(rounds: int, asr: str, tts: str = "none") -> Dict[str, Any]:
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from backend.app.adapters.asr import MockASR
    from backend.app.core import db as dbmod
    from backend.app.main import app
    from backend.app.models import LatencyMetric, Turn

    manifest = json.loads((AUDIO_DIR / "utterances.json").read_text(encoding="utf-8-sig"))
    voices: Dict[str, List[Dict[str, Any]]] = {}
    for item in manifest:
        voices.setdefault(item["voice"], []).append(item)
    client_ms: List[float] = []
    warmup_turns: set = set()
    references: Dict[str, str] = {}
    statuses: Dict[str, int] = {}
    with TestClient(app) as client:
        for rnd in range(rounds):
            for voice, items in sorted(voices.items()):
                s = client.post("/sessions", json={"channel": "mobile_voice", "consent": "granted", "lang": "en"})
                s.raise_for_status()
                sess = s.json()
                headers = {"Authorization": f"Bearer {sess['session_token']}", "Content-Type": "audio/wav"}
                for n, item in enumerate(sorted(items, key=lambda x: x["index"])):
                    body = (AUDIO_DIR / item["file"]).read_bytes()
                    patch = None
                    if asr == "mock":
                        import unittest.mock as um
                        patch = um.patch("backend.app.api.sessions.get_asr",
                                         return_value=MockASR([{"status": "transcribed", "text": item["text"],
                                                                "asr_confidence": 0.9, "poor_audio": False}]))
                        patch.start()
                    t0 = time.perf_counter()
                    r = client.post(f"/sessions/{sess['session_id']}/audio?lang=en", content=body, headers=headers)
                    elapsed = 1000 * (time.perf_counter() - t0)
                    if patch:
                        patch.stop()
                    out = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    status = out.get("status") or f"http_{r.status_code}"
                    statuses[status] = statuses.get(status, 0) + 1
                    if r.status_code != 200 or not out.get("turn_id"):
                        continue
                    references[out["turn_id"]] = item["text"]
                    if rnd == 0 and n == 0:
                        warmup_turns.add(out["turn_id"])
                        continue
                    client_ms.append(elapsed)

        async def load():
            async with dbmod.session_factory()() as db:
                metrics = list((await db.execute(select(LatencyMetric))).scalars())
                turns = list((await db.execute(select(Turn).where(Turn.speaker == "victim"))).scalars())
                return ([(m.stage, m.duration_ms, m.turn_id) for m in metrics],
                        [(t.id, t.session_id, t.seq, t.text) for t in turns])
        metrics, turns = client.portal.call(load)

    stages: Dict[str, List[float]] = {}
    for stage, ms, turn_id in metrics:
        if turn_id not in warmup_turns:
            stages.setdefault(stage, []).append(ms)
    transcripts = {tid: text for tid, _, _, text in turns}
    word_errors = [wer(ref, transcripts[tid]) for tid, ref in references.items() if tid in transcripts]         if asr != "mock" else []
    if tts == "windows_voice":
        from ml.tts.synthesize import WindowsVoiceSynthesizer, timed
        synth = WindowsVoiceSynthesizer()
        try:
            timed(synth, "Warm-up sentence.", "en")  # starts the worker; excluded like the ASR warm-up
            stages["tts_synthesis"] = [timed(synth, text, "en")[1] for _ in range(rounds) for text in TTS_SENTENCES]
        finally:
            synth.close()
    summary = {stage: summarise(v) for stage, v in sorted(stages.items())}
    summary["client_observed_request"] = summarise(client_ms)
    server_ms = summary.get("request_total", {}).get("p95")
    return {
        "benchmark": "m2-turn-latency-1.1", "asr": asr, "tts": tts, "rounds": rounds, "voices": sorted(voices),
        "utterances_per_voice": {v: len(i) for v, i in voices.items()}, "warmup_excluded": len(warmup_turns),
        "statuses": statuses, "stages_ms": summary, "budget_ms": BUDGET_MS, "not_measured": NOT_MEASURED,
        "server_path_p95_plus_configured_endpoint_ms": (round(server_ms + BUDGET_MS["vad_endpoint"], 1)
                                                        if server_ms is not None else None),
        "synthetic_speech_wer": (round(statistics.fmean(word_errors), 4) if word_errors else None),
        "evidence_class": ("synthetic speech (Windows Indian-English voices) on this laptop; fictional text; "
                           "not phone, not network, not Hindi, not human speech"),
        "machine_note": "Ryzen 7 7840HS, RTX 4060 8 GB; speech process on GPU if its environment has CUDA",
    }


def render(report: Dict[str, Any]) -> str:
    lines = ["# M2 turn-latency benchmark", "", f"ASR: `{report['asr']}` · rounds {report['rounds']} · voices "
             f"{', '.join(report['voices'])} · warm-up turns excluded {report['warmup_excluded']}", "",
             f"Evidence: {report['evidence_class']}.", "",
             "| Stage | n | p50 ms | p95 ms | max ms | Budget ms |", "|---|---|---|---|---|---|"]
    budget_of = {"safety_precheck": "safety_precheck", "dialogue_policy": "dialogue_policy",
                 "llm_phrasing": "llm_phrasing", "output_validator": "output_validator",
                 "asr_service_asr": "asr_final", "asr_request": "asr_final", "tts_synthesis": "tts_first_chunk"}
    for stage, s in report["stages_ms"].items():
        if not s.get("n"):
            continue
        b = BUDGET_MS.get(budget_of.get(stage, ""), "")
        lines.append(f"| {stage} | {s['n']} | {s['p50']} | {s['p95']} | {s['max']} | {b} |")
    lines += ["", "Not measured here:", ""] + [f"- **{k}**: {v}" for k, v in report["not_measured"].items()]
    tts = report["stages_ms"].get("tts_synthesis", {})
    if tts.get("n"):
        lines += ["", f"Offline voice (whole file = first chunk), English: p95 **{tts['p95']} ms** (budget 500 ms). "
                  "Hindi has no installed voice: those turns stay text-only."]
    lines += ["", f"Server path p95 + configured 700 ms endpoint: "
              f"**{report['server_path_p95_plus_configured_endpoint_ms']} ms** (budget 3000 ms, before TTS and LAN).",
              "", f"Synthetic-speech WER (sanity only, not M6): {report['synthetic_speech_wer']}", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="M2 turn-latency benchmark (in-process, disposable SQLite)")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--asr", choices=("local_service", "mock"), default="local_service")
    parser.add_argument("--service-url", default="http://127.0.0.1:8765")
    parser.add_argument("--tts", choices=("none", "windows_voice"), default="windows_voice",
                        help="also time the offline Windows voice on fictional reply sentences (English)")
    parser.add_argument("--db", default=str(RUNTIME_DB / "latency.db"))
    parser.add_argument("--tag", default=time.strftime("%Y-%m-%d"))
    args = parser.parse_args()
    if not (AUDIO_DIR / "utterances.json").is_file():
        raise SystemExit("run scripts\\make-benchmark-audio.ps1 first")
    prepare(Path(args.db).resolve(), args.asr, args.service_url)
    sys.path.insert(0, str(REPO))
    report = run(args.rounds, args.asr, args.tts)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = OUT_DIR / f"latency-{args.tag}-{args.asr}"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    stem.with_suffix(".md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
