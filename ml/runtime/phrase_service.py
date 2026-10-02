"""Local phrasing service: 127.0.0.1 only (EXT-132).

    python -m ml.runtime.phrase_service [--port 8766] [--models-root <models root>]

Run in the private ``sahay-ml-models`` environment. The backend's LLM adapter
(``LLM_PROVIDER=local_service``) calls it.

    GET  /health    {"status": "ready"|"loading", ...}
    POST /phrase    {"source": <approved sentence>, "register": "hi"|"en"|"hinglish"}
                    -> {"text": <one sentence>|null, "ms": float, "version": ...}

The model is Qwen3-4B-Instruct-2507 at the pinned commit, loaded in 4-bit on the GPU
(bitsandbytes NF4) or in bfloat16 on CPU when no GPU is present. It receives only the
approved sentence and a register label, never the person's own words.

Guarantees:
* binds to a loopback address only; anything else is refused before the socket opens;
* the model loads with network connections blocked, from local files only;
* request text and output are never logged or written to disk; the log line is counts only;
* one request at a time; the backend validates every output and falls back on any failure.
"""

import argparse
import importlib
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, List, Mapping, Optional

from ..llm.prompt import PROMPT_VERSION, REGISTERS, build_messages, clean_output

SERVICE_VERSION = "phrase-service-1.0"
DEFAULT_PORT = 8766
LOOPBACK_HOSTS = ("127.0.0.1", "::1")
#: The pinned checkpoint rewritten into 512 MB shards by ml.runtime.reshard (same tensors, hash-checked),
#: so it loads within a small Windows page file.
MODEL_DIR = "qwen3_4b_instruct_2507_r512"
MODEL_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
MAX_BODY = 4096
MAX_SOURCE_CHARS = 400
MAX_NEW_TOKENS = 64
#: Qwen3-Instruct-2507's recommended sampling. Wording varies from turn to turn; the
#: validator decides whether any of it may be spoken.
SAMPLING = {"do_sample": True, "temperature": 0.7, "top_p": 0.8, "top_k": 20}


class ServiceError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status, self.code = status, code


def check_bind_host(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        raise ServiceError(400, "not_loopback")
    return host


def parse_request(body: bytes) -> Mapping[str, str]:
    if len(body) > MAX_BODY:
        raise ServiceError(413, "too_large")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ServiceError(400, "bad_json") from None
    if not isinstance(data, dict):
        raise ServiceError(400, "bad_json")
    source, register = data.get("source"), data.get("register")
    if not isinstance(source, str) or not source.strip() or len(source) > MAX_SOURCE_CHARS:
        raise ServiceError(400, "bad_source")
    if register not in REGISTERS:
        raise ServiceError(400, "bad_register")
    return {"source": source, "register": register}


class PhraseEngine:
    """Tokenizer + model. ``generate`` is injectable for tests."""

    def __init__(self, generate: Any = None, *, models_root: Optional[str] = None) -> None:
        self._generate = generate
        self._models_root = models_root
        self.lock = threading.Lock()
        self.ready = generate is not None
        self.device = "injected" if generate is not None else "unloaded"

    def load(self) -> None:
        # Loaded lazily, like the rest of ml/runtime: importing this module loads no Torch.
        torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
        AutoModelForCausalLM, AutoTokenizer = transformers.AutoModelForCausalLM, transformers.AutoTokenizer

        root = self._models_root or os.environ.get("SAHAY_MODELS_ROOT", "")
        if not root:
            raise RuntimeError("SAHAY_MODELS_ROOT is not set")
        path = os.path.join(root, MODEL_DIR)
        tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        if torch.cuda.is_available():
            quant = transformers.BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                       bnb_4bit_compute_dtype=torch.float16)
            model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True,
                                                         quantization_config=quant, device_map="cuda:0")
            self.device = "cuda-nf4"
        else:
            model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, dtype=torch.bfloat16)
            self.device = "cpu-bf16"
        model.eval()

        def generate(messages: List[Mapping[str, str]]) -> str:
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            with torch.inference_mode():
                out = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS,
                                     pad_token_id=tokenizer.eos_token_id, **SAMPLING)
            return tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        self._generate = generate
        self.ready = True

    def phrase(self, source: str, register: str) -> Optional[str]:
        return clean_output(self._generate(build_messages(source, register)))


def phrase_request(engine: PhraseEngine, body: bytes) -> Mapping[str, Any]:
    req = parse_request(body)
    started = time.perf_counter()
    text = engine.phrase(req["source"], req["register"])
    return {"text": text, "ms": round(1000 * (time.perf_counter() - started), 1),
            "version": SERVICE_VERSION, "prompt": PROMPT_VERSION}


def make_handler(engine: PhraseEngine) -> type:
    class Handler(BaseHTTPRequestHandler):
        server_version = "sahay-phrase/1.0"
        sys_version = ""

        def _send(self, status: int, payload: Mapping[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args: Any) -> None:  # never the body
            return

        def do_GET(self) -> None:
            if self.path != "/health":
                return self._send(404, {"error": "not_found"})
            self._send(200, {"status": "ready" if engine.ready else "loading", "version": SERVICE_VERSION,
                             "prompt": PROMPT_VERSION, "device": engine.device, "model_revision": MODEL_REVISION})

        def do_POST(self) -> None:
            if self.path != "/phrase":
                return self._send(404, {"error": "not_found"})
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(min(length, MAX_BODY + 1)) if length else b""
            try:
                with engine.lock:
                    status, payload = 200, phrase_request(engine, body)
            except ServiceError as exc:
                status, payload = exc.status, {"error": exc.code}
            except Exception as exc:  # the type only: never the text
                status, payload = 500, {"error": "inference_failed", "type": type(exc).__name__}
            self._send(status, payload)
            print(json.dumps({"request": "phrase", "http": status, "ms": payload.get("ms"),
                              "empty": payload.get("text") is None}), flush=True)

    return Handler


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.runtime.phrase_service", description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--models-root", default=None)
    args = parser.parse_args(argv)
    host = check_bind_host(args.host)
    from .offline import apply_offline_env, network_blocked

    engine = PhraseEngine(models_root=args.models_root)
    apply_offline_env()
    with network_blocked() as net:
        engine.load()
    if net["attempts"]:
        print(json.dumps({"status": "refused", "reason": "a network attempt was made while loading the model"}))
        return 1
    server = HTTPServer((host, args.port), make_handler(engine))
    print(json.dumps({"status": "ready", "listening": f"http://{host}:{args.port}", "device": engine.device,
                      "version": SERVICE_VERSION}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
