"""Advisory model signals for officers: 127.0.0.1 only (EXT-133, PC-14).

    python -m ml.shadow.service [--port 8767] [--training-root <training root>]

Run in the private ``sahay-ml-models`` environment with ``SAHAY_TRAINING_ROOT`` set. The
backend's signal adapter (``SIGNALS_PROVIDER=local_service``) calls it from the background
assessment cycle, never from the reply path.

    GET  /health     {"status": "ready"|"loading", ...}
    POST /signals    {"texts": [<victim turn>, ...]}  ->  signal payload (see ``to_signal``)

The model is the task7b experimental shadow classifier (MuRIL encoder, multi-label head),
status ``rejected_for_product_integration``. Only the three labels that passed their measured
gates are returned; the others are dropped here, before anything leaves the process. The
output is advisory and uncalibrated: it never changes routing, the band, the SVI, alerts,
the crisis interrupt or anything said to the victim, and it never reaches the victim.

Guarantees: loopback only; offline load with the network blocked; no text logged; one
request at a time.
"""

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Mapping, Optional, Sequence

SERVICE_VERSION = "signal-service-1.0"
DEFAULT_PORT = 8767
LOOPBACK_HOSTS = ("127.0.0.1", "::1")
CHECKPOINT_SET = "task7b"
#: Labels with measured support that passed their gates (EXT-133). Nothing else is returned.
SHOWN_LABELS = ("crisis_self_harm", "communication_safety_coercion", "legal_urgency")
MAX_BODY = 64 * 1024
MAX_TURNS = 40


class ServiceError(Exception):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status, self.code = status, code


def check_bind_host(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        raise ServiceError(400, "not_loopback")
    return host


def parse_request(body: bytes) -> List[str]:
    if len(body) > MAX_BODY:
        raise ServiceError(413, "too_large")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ServiceError(400, "bad_json") from None
    texts = data.get("texts") if isinstance(data, dict) else None
    if not isinstance(texts, list) or not texts or len(texts) > MAX_TURNS \
            or not all(isinstance(t, str) for t in texts):
        raise ServiceError(400, "bad_texts")
    return texts


def to_signal(result: Mapping[str, Any]) -> Dict[str, Any]:
    """The PC-14 payload from a shadow result: shown labels only, advisory, uncalibrated."""
    status = result.get("status")
    out: Dict[str, Any] = {
        "status": status if status in ("loaded", "unavailable", "failed") else "failed",
        "model": "experimental_shadow_classifier",
        "checkpoint_status": str(result.get("deployment_status") or "rejected_for_product_integration"),
        "advisory": True,
        "uncalibrated": True,
        "labels": {},
    }
    probs, fired = result.get("probabilities") or {}, result.get("development_firings") or {}
    if out["status"] == "loaded":
        for label in SHOWN_LABELS:
            if isinstance(probs.get(label), (int, float)):
                out["labels"][label] = {"probability": round(float(probs[label]), 4),
                                        "fired": bool(fired.get(label))}
    return out


class SignalEngine:
    """Wraps the shadow classifier. ``classify`` is injectable for tests."""

    def __init__(self, classify: Any = None, *, training_root: Optional[str] = None) -> None:
        self._classify = classify
        self._root = training_root
        self.lock = threading.Lock()
        self.ready = classify is not None

    def load(self) -> Dict[str, Any]:
        from .classifier import ShadowClassifier

        clf = ShadowClassifier(training_root=self._root, checkpoint_set=CHECKPOINT_SET)
        state = clf.load()
        self._classify = lambda texts: clf.classify([{"speaker": "victim", "text": t} for t in texts]).__dict__
        self.ready = state.status == "loaded"
        return {"status": state.status, "reason": getattr(state, "reason", None)}

    def signals(self, texts: Sequence[str]) -> Dict[str, Any]:
        return to_signal(self._classify(list(texts)))


def make_handler(engine: SignalEngine) -> type:
    class Handler(BaseHTTPRequestHandler):
        server_version = "sahay-signal/1.0"
        sys_version = ""

        def _send(self, status: int, payload: Mapping[str, Any]) -> None:
            data = json.dumps(payload).encode("utf-8")
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
                             "labels": list(SHOWN_LABELS)})

        def do_POST(self) -> None:
            if self.path != "/signals":
                return self._send(404, {"error": "not_found"})
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(min(length, MAX_BODY + 1)) if length else b""
            try:
                texts = parse_request(body)
                with engine.lock:
                    status, payload = 200, engine.signals(texts)
            except ServiceError as exc:
                status, payload = exc.status, {"error": exc.code}
            except Exception as exc:  # the type only: never the text
                status, payload = 500, {"error": "inference_failed", "type": type(exc).__name__}
            self._send(status, payload)
            print(json.dumps({"request": "signals", "http": status, "status": payload.get("status")}), flush=True)

    return Handler


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.shadow.service", description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--training-root", default=None)
    args = parser.parse_args(argv)
    host = check_bind_host(args.host)
    from ..runtime.offline import apply_offline_env, network_blocked

    engine = SignalEngine(training_root=args.training_root)
    apply_offline_env()
    with network_blocked() as net:
        state = engine.load()
    if net["attempts"] or not engine.ready:
        print(json.dumps({"status": "refused", "load": state, "network_attempts": net["attempts"]}))
        return 1
    server = HTTPServer((host, args.port), make_handler(engine))
    print(json.dumps({"status": "ready", "listening": f"http://{host}:{args.port}", "version": SERVICE_VERSION}),
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
