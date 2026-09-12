"""Model-runtime tests. Offline, model-free and GPU-free: every backend here is a small fake.

Real-model checks live behind ``python -m ml.runtime.verify_models`` and benchmarks behind
``python -m ml.runtime.benchmark``; nothing in this file downloads, loads or needs a model.
"""

import copy
import hashlib
import inspect
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest import mock

from ml.assessment import assess
from ml.eval import checks
from ml.eval.evaluate import evaluate
from ml.guardrails import crisis_check
from ml.runtime import audio as au, config, device as dev, status as st
from ml.runtime.asr import TASK, WhisperASR
from ml.runtime.fixtures import SENTENCES, build_text
from ml.runtime.offline import NetworkBlocked, network_blocked
from ml.runtime.pipeline import GatedTranscriber
from ml.runtime.text_encoder import ENCODER_ROLES, MAX_BATCH, TextEncoder
from ml.runtime.vad import SileroVAD

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent
RUNTIME = ML / "runtime"
HEAVY = ("torch", "torchaudio", "transformers", "faster_whisper", "ctranslate2", "silero_vad", "numpy",
         "huggingface_hub", "onnxruntime", "tokenizers", "psutil")
SECRET_SENTENCE = "a private sentence that must never be echoed"


# --- fakes ----------------------------------------------------------------------------------------


class FakeEncoderBackend:
    instances = 0

    def __init__(self, directory, choice, fail_with=None):
        FakeEncoderBackend.instances += 1
        self.choice = choice
        self.unk_id = 0
        self.batches = []
        self.fail_with = fail_with
        self.closed = False

    def token_ids(self, texts, max_length):
        return [[101] + [1 + (ord(c) % 50) for c in t.split()[0]] + [0] + [102] for t in texts]

    def embed(self, texts, max_length):
        if self.fail_with is not None:
            raise self.fail_with
        self.batches.append(len(texts))
        return [[float(int(hashlib.sha256(t.encode()).hexdigest()[i:i + 2], 16)) / 255 for i in range(0, 16, 2)]
                for t in texts]

    def close(self):
        self.closed = True


class FakeASRBackend:
    instances = 0

    def __init__(self, directory, choice, compute_type, fail_with=None):
        FakeASRBackend.instances += 1
        self.calls = []
        self.fail_with = fail_with
        self.closed = False

    def transcribe(self, samples, **options):
        self.calls.append({**options, "_samples": len(samples)})
        if self.fail_with is not None:
            raise self.fail_with
        from ml.runtime.asr import ASRSegment
        return [ASRSegment(0.0, 1.0, "fictional words")], {"language": options["language"],
                                                         "language_probability": 0.9}

    def close(self):
        self.closed = True


class FakeVADBackend:
    def __init__(self, spans=((0.5, 1.5),)):
        self.calls = 0
        self.spans = list(spans)

    def speech_timestamps(self, samples):
        self.calls += 1
        return self.spans

    def close(self):
        pass


class FakeTorch:
    class cuda:
        available = False

        @classmethod
        def is_available(cls):
            return cls.available

        @staticmethod
        def device_count():
            return 1


CPU = dev.DeviceChoice("cpu", "float32", True, "cuda_unavailable_cpu_fallback")


def blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class RootCase(unittest.TestCase):
    """A temporary model root holding tiny fake files that match a fake manifest."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.manifest = copy.deepcopy(config.load_manifest())
        self.files = {}
        for entry in self.manifest["models"]:
            if entry["source"] != "huggingface":
                continue
            rows = []
            for i, name in enumerate(("config.json", "weights.bin")):
                data = f"{entry['logical_id']}:{name}:{i}".encode()
                row = {"path": name, "bytes": len(data)}
                row.update({"sha256": hashlib.sha256(data).hexdigest()} if name.endswith(".bin")
                           else {"git_blob_sha1": blob_sha1(data)})
                rows.append(row)
                target = config.model_dir(self.root, entry) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            entry["files"] = rows
        whisper = config.get_model(self.manifest, "whisper_small")
        ddir = config.derived_dir(self.root, whisper)
        ddir.mkdir(parents=True)
        for name in ("model.bin", "config.json", "vocabulary.json", "tokenizer.json", "preprocessor_config.json"):
            (ddir / name).write_bytes(b"x")
        env = mock.patch.dict(os.environ, {config.ROOT_ENV: str(self.root)})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def encoder(self, name="muril", **kw):
        kw.setdefault("backend_factory", FakeEncoderBackend)
        return TextEncoder(name, manifest=self.manifest, device_choice=CPU, **kw)

    def asr(self, **kw):
        kw.setdefault("backend_factory", FakeASRBackend)
        return WhisperASR(manifest=self.manifest, device_choice=CPU, **kw)


# --- root, confinement, manifest ------------------------------------------------------------------


class TestRootAndConfinement(unittest.TestCase):
    def test_the_root_environment_variable_is_required(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(config.ROOT_ENV, None)
            with self.assertRaises(config.RuntimeConfigError) as ctx:
                config.models_root()
        self.assertIn(config.ROOT_ENV, str(ctx.exception))

    def test_a_missing_root_is_refused_without_echoing_the_path(self):
        with self.assertRaises(config.RuntimeConfigError) as ctx:
            config.models_root(str(Path(tempfile.gettempdir()) / "sahay-no-such-root-xyz"))
        self.assertNotIn("sahay-no-such-root-xyz", str(ctx.exception))

    def test_a_root_inside_the_checkout_is_refused(self):
        with self.assertRaises(config.RuntimeConfigError):
            config.models_root(str(ML))

    def test_paths_are_confined_beneath_the_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.assertEqual(config.confined(root, "a", "b"), root / "a" / "b")
            for bad in (("..", "x"), ("a", "..", "..", "x"), ("/etc",), ("C:/Windows",), ("",)):
                with self.assertRaises(config.RuntimeConfigError, msg=bad):
                    config.confined(root, *bad)

    def test_code_carries_no_machine_specific_default(self):
        for path in RUNTIME.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"[A-Za-z]:[\\/]+(Code|Users)[\\/]|sih-dataset|/home/[a-z]", text), path.name)


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = config.load_manifest()

    def test_the_committed_manifest_is_valid_and_complete(self):
        self.assertEqual(config.validate_manifest(self.manifest), [])
        ids = {m["logical_id"] for m in self.manifest["models"]}
        self.assertEqual(ids, {"muril_base_cased", "xlm_roberta_base", "whisper_small", "silero_vad"})
        for m in self.manifest["models"]:
            for field in ("upstream_repo", "revision", "purpose", "licence", "architecture", "claimed_languages",
                          "expected_input", "local_env", "integrity", "approval_status"):
                self.assertTrue(m[field], (m["logical_id"], field))
            self.assertFalse(m["fine_tuned_for_sahay"])

    def test_every_revision_is_an_immutable_commit(self):
        for m in self.manifest["models"]:
            self.assertRegex(m["revision"], r"^[0-9a-f]{40}$")
        bad = copy.deepcopy(self.manifest)
        bad["models"][0]["revision"] = "main"
        self.assertTrue(any("immutable" in e for e in config.validate_manifest(bad)))

    def test_gated_token_or_fine_tuned_entries_are_refused(self):
        for field, value in (("gated", True), ("token_required", True), ("fine_tuned_for_sahay", True),
                             ("licence", "proprietary"), ("approval_status", "proposed")):
            bad = copy.deepcopy(self.manifest)
            bad["models"][0][field] = value
            self.assertTrue(config.validate_manifest(bad), field)

    def test_machine_paths_and_ambiguous_hashes_are_refused(self):
        bad = copy.deepcopy(self.manifest)
        bad["models"][0]["purpose"] = "see " + "C:" + "\\models\\muril"
        self.assertTrue(any("machine" in e for e in config.validate_manifest(bad)))
        bad = copy.deepcopy(self.manifest)
        bad["models"][0]["files"][0]["sha256"] = "0" * 64
        self.assertTrue(any("exactly one" in e for e in config.validate_manifest(bad)))
        bad = copy.deepcopy(self.manifest)
        bad["models"][0]["files"][0]["path"] = "../escape.json"
        self.assertTrue(config.validate_manifest(bad))

    def test_model_roles_are_separated(self):
        roles = {m["logical_id"]: m["role"] for m in self.manifest["models"]}
        self.assertEqual(roles["muril_base_cased"], "primary_text_encoder")
        self.assertEqual(roles["xlm_roberta_base"], "comparison_text_encoder")
        self.assertEqual(ENCODER_ROLES, {"muril_base_cased": "primary_text_encoder",
                                         "xlm_roberta_base": "comparison_text_encoder"})
        bad = copy.deepcopy(self.manifest)
        bad["models"][1]["role"] = "primary_text_encoder"
        self.assertTrue(any("exactly one" in e for e in config.validate_manifest(bad)))

    def test_the_requirements_are_exact_and_exclude_training_tools(self):
        text = (RUNTIME / "requirements-models.txt").read_text(encoding="utf-8")
        reqs = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith(("#", "--"))]
        self.assertTrue(reqs)
        for line in reqs:
            self.assertRegex(line, r"^[A-Za-z0-9_.\-]+==[0-9][^\s]*$", line)
        names = {ln.split("==")[0].lower() for ln in reqs}
        for banned in ("peft", "trl", "deepspeed", "vllm", "bitsandbytes", "jupyter", "notebook", "openai"):
            self.assertNotIn(banned, names)


class TestIntegrity(RootCase):
    def test_git_blob_ids_match_git(self):
        path = self.root / "hello.txt"
        path.write_bytes(b"hello\n")
        self.assertEqual(config.git_blob_sha1(path), "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_verified_files_pass_and_tampering_fails(self):
        entry = config.get_model(self.manifest, "muril_base_cased")
        directory = config.model_dir(self.root, entry)
        self.assertTrue(config.verify_files(directory, entry["files"])["ok"])
        weights = directory / "weights.bin"
        data = bytearray(weights.read_bytes())
        data[0] ^= 1
        weights.write_bytes(bytes(data))
        result = config.verify_files(directory, entry["files"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["hash_mismatch"], ["weights.bin"])
        (directory / "config.json").unlink()
        self.assertEqual(config.verify_files(directory, entry["files"])["missing"], ["config.json"])

    def test_a_corrupt_model_is_unavailable_rather_than_loaded(self):
        entry = config.get_model(self.manifest, "muril_base_cased")
        (config.model_dir(self.root, entry) / "weights.bin").write_bytes(b"truncated")
        enc = self.encoder()
        self.assertEqual(enc.status().state, st.UNAVAILABLE)
        with self.assertRaises(st.RuntimeFailure) as ctx:
            enc.load()
        self.assertEqual(ctx.exception.code, "unavailable")


# --- laziness, offline -----------------------------------------------------------------------------


class TestLaziness(unittest.TestCase):
    def test_importing_the_runtime_imports_no_heavy_package(self):
        modules = sorted(p.stem for p in RUNTIME.glob("*.py") if p.stem != "__init__")
        code = ("import sys\n" + "".join(f"import ml.runtime.{m}\n" for m in modules)
                + f"print(sorted(set({HEAVY!r}) & set(m.split('.')[0] for m in sys.modules)))")
        out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        self.assertEqual(out.stdout.strip(), "[]")

    def test_constructing_an_adapter_loads_nothing(self):
        FakeEncoderBackend.instances = 0
        TextEncoder("muril", backend_factory=FakeEncoderBackend)
        WhisperASR(backend_factory=FakeASRBackend)
        SileroVAD(backend_factory=FakeVADBackend)
        self.assertEqual(FakeEncoderBackend.instances, 0)

    def test_no_implicit_download_path_exists(self):
        for path in RUNTIME.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if path.name != "download.py":
                self.assertFalse("snapshot_download" in text, path.name)
                self.assertFalse("hf_hub_download" in text, path.name)
                self.assertNotRegex(text, r"^\s*(from|import)\s+\.download\b", path.name)
            self.assertFalse("torch.hub" in text, path.name)
        for name in ("text_encoder.py", "asr.py"):
            self.assertIn("local_files_only=True", (RUNTIME / name).read_text(encoding="utf-8"))
        self.assertIn("token=False", (RUNTIME / "download.py").read_text(encoding="utf-8"))

    def test_the_network_block_refuses_and_counts_then_restores(self):
        original = socket.create_connection
        with network_blocked() as net:
            self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), "1")
            with self.assertRaises(NetworkBlocked):
                socket.create_connection(("example.invalid", 443), timeout=1)
            with self.assertRaises(NetworkBlocked):
                socket.getaddrinfo("example.invalid", 443)
        self.assertEqual(net["attempts"], 2)
        self.assertIs(socket.create_connection, original)


# --- device selection -------------------------------------------------------------------------------


class TestDevice(unittest.TestCase):
    def test_cuda_is_chosen_only_when_available(self):
        FakeTorch.cuda.available = True
        self.assertEqual(dev.select_device("auto", FakeTorch), dev.DeviceChoice("cuda", "float16", False,
                                                                                "cuda_available"))
        FakeTorch.cuda.available = False
        choice = dev.select_device("auto", FakeTorch)
        self.assertEqual((choice.device, choice.precision, choice.degraded), ("cpu", "float32", True))
        self.assertTrue(dev.select_device("cuda", FakeTorch).degraded)

    def test_cpu_request_and_invalid_request(self):
        self.assertFalse(dev.select_device("cpu").degraded)
        with self.assertRaises(ValueError):
            dev.select_device("tpu")

    def test_a_broken_driver_degrades_instead_of_crashing(self):
        class Broken:
            class cuda:
                @staticmethod
                def is_available():
                    raise RuntimeError("driver")
        self.assertEqual(dev.select_device("auto", Broken).device, "cpu")

    def test_out_of_memory_is_recognised(self):
        self.assertTrue(dev.is_out_of_memory(RuntimeError("CUDA out of memory. Tried to allocate")))
        self.assertTrue(dev.is_out_of_memory(type("OutOfMemoryError", (Exception,), {})()))
        self.assertFalse(dev.is_out_of_memory(ValueError("bad shape")))


# --- text encoder ------------------------------------------------------------------------------------


class TestTextEncoder(RootCase):
    def test_a_missing_model_is_unavailable_not_zero(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(config.ROOT_ENV, None)
            enc = TextEncoder("muril", manifest=self.manifest, backend_factory=FakeEncoderBackend)
            self.assertEqual(enc.status().state, st.UNAVAILABLE)
            with self.assertRaises(st.RuntimeFailure) as ctx:
                enc.encode(["text"])
        self.assertEqual(ctx.exception.code, "unavailable")

    def test_loading_is_explicit_and_happens_once(self):
        FakeEncoderBackend.instances = 0
        enc = self.encoder()
        self.assertEqual(enc.status().state, st.AVAILABLE)
        self.assertEqual(FakeEncoderBackend.instances, 0)
        enc.load()
        enc.load()
        self.assertEqual(FakeEncoderBackend.instances, 1)
        self.assertEqual(enc.status().state, st.LOADED)

    def test_embeddings_are_deterministic_and_carry_no_decision(self):
        enc = self.encoder()
        enc.load()
        a = enc.encode(["same input"])
        b = enc.encode(["same input"])
        self.assertEqual(a.embeddings, b.embeddings)
        summary = a.summary()
        st.assert_no_decision_keys(summary)
        self.assertNotIn("embeddings", summary)
        self.assertFalse(a.fine_tuned_for_sahay)
        self.assertIn("unfine-tuned", a.note)
        self.assertTrue(a.degraded)

    def test_batches_are_bounded(self):
        enc = self.encoder()
        enc.load()
        out = enc.encode([f"text {i}" for i in range(40)])
        self.assertEqual(len(out.embeddings), 40)
        self.assertTrue(all(n <= MAX_BATCH for n in enc._backend.batches))

    def test_roles_are_separate_and_unknown_models_refused(self):
        self.assertEqual(self.encoder("muril").role, "primary_text_encoder")
        self.assertEqual(self.encoder("xlmr").role, "comparison_text_encoder")
        for bad in ("whisper_small", "indicbert", "qwen"):
            with self.assertRaises(st.RuntimeFailure):
                TextEncoder(bad)

    def test_invalid_input_is_refused(self):
        enc = self.encoder()
        enc.load()
        for bad in ("a bare string", [], [""], [3], ["ok", "   "]):
            with self.assertRaises(st.RuntimeFailure):
                enc.encode(bad)
        with self.assertRaises(st.RuntimeFailure):
            enc.encode(["ok"], max_length=4096)

    def test_errors_never_echo_the_input(self):
        failing = partial(FakeEncoderBackend, fail_with=ValueError(f"cannot handle {SECRET_SENTENCE}"))
        enc = self.encoder(backend_factory=failing)
        enc.load()
        with self.assertRaises(st.RuntimeFailure) as ctx:
            enc.encode([SECRET_SENTENCE])
        self.assertEqual(ctx.exception.code, "inference_failed")
        self.assertNotIn(SECRET_SENTENCE, str(ctx.exception))
        self.assertNotIn("private sentence", repr(ctx.exception.args))

    def test_out_of_memory_releases_the_model(self):
        failing = partial(FakeEncoderBackend, fail_with=RuntimeError("CUDA out of memory"))
        enc = self.encoder(backend_factory=failing)
        enc.load()
        with self.assertRaises(st.RuntimeFailure) as ctx:
            enc.encode(["text"])
        self.assertEqual(ctx.exception.code, "resource_exhausted")
        self.assertFalse(enc.loaded)

    def test_unload_closes_the_backend(self):
        enc = self.encoder()
        enc.load()
        backend = enc._backend
        enc.unload()
        self.assertTrue(backend.closed)
        self.assertFalse(enc.loaded)
        self.assertEqual(enc.status().state, st.AVAILABLE)

    def test_an_offline_reload_makes_no_network_attempt(self):
        with network_blocked() as net:
            enc = self.encoder()
            enc.load()
            enc.encode(["one"])
            enc.unload()
            enc.load()
            enc.unload()
        self.assertEqual(net["attempts"], 0)

    def test_load_failures_are_redacted(self):
        def broken(directory, choice):
            raise OSError(f"cannot open {directory}/weights.bin with hf_abcdefghijklmnop")
        enc = self.encoder(backend_factory=broken)
        with self.assertRaises(st.RuntimeFailure) as ctx:
            enc.load()
        text = str(ctx.exception)
        self.assertEqual(ctx.exception.code, "load_failed")
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("hf_abcdefghijklmnop", text)


# --- ASR: the public, VAD-gated boundary -----------------------------------------------------------------


class TestASRPublicBoundary(RootCase):
    """Task 6A: Whisper is reachable only with validated VAD intervals."""

    def setUp(self):
        super().setUp()
        FakeASRBackend.instances = 0

    def test_omitting_speech_intervals_is_rejected_by_the_signature(self):
        param = inspect.signature(WhisperASR.transcribe).parameters["speech_intervals"]
        self.assertIs(param.default, inspect.Parameter.empty)
        asr = self.asr()
        asr.load()
        with self.assertRaises(TypeError):
            asr.transcribe(au.silence(1), "hi")  # pylint: disable=no-value-for-parameter
        self.assertEqual(asr._backend.calls, [])

    def test_none_is_refused_before_any_decoder_work(self):
        unloaded = self.asr()
        with self.assertRaises(st.RuntimeFailure) as ctx:
            unloaded.transcribe(au.silence(1), "hi", None)
        self.assertEqual(ctx.exception.code, "vad_required")
        self.assertEqual(FakeASRBackend.instances, 0)  # no decoder was even constructed
        loaded = self.asr()
        loaded.load()
        with self.assertRaises(st.RuntimeFailure) as ctx:
            loaded.transcribe(au.silence(1), "hi", speech_intervals=None)
        self.assertEqual(ctx.exception.code, "vad_required")
        self.assertEqual(loaded._backend.calls, [])

    def test_empty_intervals_return_a_structured_no_speech_result(self):
        asr = self.asr()  # deliberately not loaded: no speech needs no decoder
        result = asr.transcribe(au.silence(2), "hi", [])
        self.assertEqual((result.status, result.text, result.segments), ("no_speech", "", []))
        self.assertEqual((result.intervals_detected, result.intervals_decoded), (0, 0))
        self.assertFalse(result.decoder_invoked)
        self.assertTrue(result.vad_gated)
        self.assertFalse(result.benchmark_only)
        self.assertIsNone(result.calibrated_confidence)
        self.assertEqual(result.requested_language, "hi")
        self.assertIn("no D4", result.scope_note)
        self.assertEqual(FakeASRBackend.instances, 0)
        loaded = self.asr()
        loaded.load()
        loaded.transcribe(au.silence(2), "en", [])
        self.assertEqual(loaded._backend.calls, [])

    def test_successful_public_results_are_always_vad_gated(self):
        asr = self.asr()
        asr.load()
        for spans in ([(0.5, 1.0)], [(0.0, 0.5), (0.5, 1.0)], [(1.5, 3.0)]):
            result = asr.transcribe(au.silence(3), "hi", spans)
            self.assertEqual(result.status, "transcribed")
            self.assertTrue(result.vad_gated)
            self.assertFalse(result.benchmark_only)
            self.assertTrue(result.decoder_invoked)
            self.assertEqual(result.intervals_decoded, len(spans))

    def test_no_bypass_flag_exists_on_the_public_method(self):
        params = set(inspect.signature(WhisperASR.transcribe).parameters)
        self.assertEqual(params, {"self", "samples", "language", "speech_intervals", "sample_rate"})
        banned = re.compile(r"\b(skip_vad|disable_vad|force_decode|allow_ungated|benchmark_mode)\b|\bunsafe\s*[=:]")
        for path in RUNTIME.glob("*.py"):
            self.assertIsNone(banned.search(path.read_text(encoding="utf-8")), path.name)

    def test_the_cli_exposes_no_ungated_production_option(self):
        for name in ("verify_models.py", "benchmark.py", "download.py", "hardware.py"):
            text = (RUNTIME / name).read_text(encoding="utf-8")
            options = re.findall(r"add_argument\(\s*\"(--[\w-]+)\"", text)
            for option in options:
                self.assertIsNone(re.search(r"vad|gate|skip|force|unsafe|raw", option), (name, option))
        verify = (RUNTIME / "verify_models.py").read_text(encoding="utf-8")
        self.assertNotIn("_transcribe_ungated_for_benchmark", verify)
        self.assertNotIn("worst-case", verify)

    def test_the_task_is_always_transcribe_in_the_named_language(self):
        asr = self.asr()
        asr.load()
        for lang in ("hi", "en"):
            result = asr.transcribe(au.silence(2), lang, [(0.5, 1.5)])
            options = asr._backend.calls[-1]
            self.assertEqual(options["task"], "transcribe")
            self.assertEqual(options["language"], lang)
            self.assertNotIn("clip_timestamps", options)
            self.assertEqual((result.task, result.requested_language), (TASK, lang))
        self.assertNotIn('"translate"', (RUNTIME / "asr.py").read_text(encoding="utf-8"))

    def test_unsupported_or_missing_languages_are_refused(self):
        asr = self.asr()
        asr.load()
        for bad in ("fr", "auto", None, "hin"):
            with self.assertRaises(st.RuntimeFailure) as ctx:
                asr.transcribe(au.silence(1), bad, [(0.1, 0.5)])
            self.assertEqual(ctx.exception.code, "unsupported_language")
        self.assertEqual(asr._backend.calls, [])

    def test_sample_rate_and_shape_are_validated(self):
        asr = self.asr()
        asr.load()
        with self.assertRaises(st.RuntimeFailure) as ctx:
            asr.transcribe(au.silence(1), "hi", [], sample_rate=8000)
        self.assertEqual(ctx.exception.code, "unsupported_sample_rate")
        stereo = type("Stereo", (), {"ndim": 2, "__len__": lambda self: 10})()
        with self.assertRaises(st.RuntimeFailure) as ctx:
            asr.transcribe(stereo, "hi", [])
        self.assertEqual(ctx.exception.code, "invalid_input")
        self.assertEqual(asr._backend.calls, [])

    def test_no_calibrated_confidence_is_invented_and_the_summary_hides_text(self):
        asr = self.asr()
        asr.load()
        result = asr.transcribe(au.silence(2), "hi", [(0.5, 1.5)])
        self.assertIsNone(result.calibrated_confidence)
        self.assertIn("uncalibrated", result.confidence_note)
        summary = result.summary()
        self.assertNotIn("text", summary)
        self.assertNotIn("fictional words", json.dumps(summary))
        st.assert_no_decision_keys(summary)

    def test_failures_are_redacted_and_out_of_memory_unloads(self):
        leaky = partial(FakeASRBackend, fail_with=RuntimeError(f"decoder saw {SECRET_SENTENCE}"))
        asr = self.asr(backend_factory=leaky)
        asr.load()
        with self.assertRaises(st.RuntimeFailure) as ctx:
            asr.transcribe(au.silence(2), "hi", [(0.5, 1.5)])
        self.assertNotIn(SECRET_SENTENCE, str(ctx.exception))
        oom = partial(FakeASRBackend, fail_with=RuntimeError("CUDA failed with error out of memory"))
        asr = self.asr(backend_factory=oom)
        asr.load()
        with self.assertRaises(st.RuntimeFailure) as ctx:
            asr.transcribe(au.silence(2), "hi", [(0.5, 1.5)])
        self.assertEqual(ctx.exception.code, "resource_exhausted")
        self.assertFalse(asr.loaded)

    def test_one_worker_cpu_int8_fallback_and_cleanup(self):
        from ml.runtime import asr as asr_mod
        self.assertEqual(asr_mod.WORKERS, 1)
        asr = self.asr()
        asr.load()
        self.assertEqual(asr.compute_type, "int8")
        self.assertTrue(asr.status().degraded)
        backend = asr._backend
        asr.unload()
        self.assertTrue(backend.closed)
        self.assertFalse(asr.loaded)

    def test_cuda_selects_fp16(self):
        cuda = dev.DeviceChoice("cuda", "float16", False, "cuda_available")
        asr = WhisperASR(manifest=self.manifest, device_choice=cuda, backend_factory=FakeASRBackend)
        asr.load()
        self.assertEqual(asr.compute_type, "float16")
        self.assertFalse(asr.status().degraded)

    def test_missing_conversion_is_unavailable(self):
        whisper = config.get_model(self.manifest, "whisper_small")
        (config.derived_dir(self.root, whisper) / "model.bin").unlink()
        self.assertEqual(self.asr().status().state, st.UNAVAILABLE)


class TestIntervalValidation(RootCase):
    """Every rule is checked across the whole list before the first decoder call."""

    def loaded(self):
        asr = self.asr()
        asr.load()
        return asr

    def refused(self, spans, audio_s=3.0):
        asr = self.loaded()
        with self.assertRaises(st.RuntimeFailure) as ctx:
            asr.transcribe(au.silence(audio_s), "hi", spans)
        self.assertEqual(asr._backend.calls, [], spans)  # the decoder never ran
        return ctx.exception

    def test_negative_start_and_end(self):
        self.assertIn("negative", str(self.refused([(-0.1, 1.0)])))
        self.assertIn("negative", str(self.refused([(0.5, -0.2)])))

    def test_end_before_start(self):
        self.assertIn("end before start", str(self.refused([(1.0, 0.5)])))

    def test_zero_length_is_refused_because_the_vad_never_emits_one(self):
        self.assertIn("zero-length", str(self.refused([(1.0, 1.0)])))
        self.assertIn("does not map", str(self.refused([(0.00001, 0.00002)])))

    def test_out_of_range_end_is_refused_and_the_exact_end_is_accepted(self):
        self.assertIn("beyond the audio", str(self.refused([(2.0, 3.5)])))
        asr = self.loaded()
        self.assertTrue(asr.transcribe(au.silence(3), "hi", [(2.0, 3.0)]).vad_gated)

    def test_non_finite_values(self):
        for bad in ((math.nan, 1.0), (0.5, math.inf), (-math.inf, 1.0)):
            self.assertIn("non-finite", str(self.refused([bad])))

    def test_wrong_value_types(self):
        for bad in (("0.5", "1.0"), (True, 1.0), (0.5, None), (0.5, [1.0])):
            self.assertIn("numbers", str(self.refused([bad])))
        for container in ("0.5-1.0", {"start": 0.5, "end": 1.0}, 7, (s for s in [(0.5, 1.0)])):
            exc = self.refused(container)
            self.assertEqual(exc.code, "invalid_intervals")

    def test_missing_or_malformed_interval_fields(self):
        for bad in ((0.5,), (), (0.5, 1.0, 2.0), {"start": 0.5, "end": 1.0}, "01", 0.5):
            self.assertIn("pair", str(self.refused([bad])))

    def test_descending_overlapping_and_duplicate_intervals(self):
        self.assertIn("ascending", str(self.refused([(2.0, 2.5), (0.5, 1.0)])))
        self.assertIn("overlaps", str(self.refused([(0.5, 1.5), (1.0, 2.0)])))
        self.assertIn("duplicate", str(self.refused([(0.5, 1.0), (0.5, 1.0)])))

    def test_a_later_invalid_interval_prevents_every_decoder_call(self):
        exc = self.refused([(0.2, 0.8), (1.0, 1.5), (2.0, 9.0)])
        self.assertIn("interval 2", str(exc))

    def test_errors_name_the_rule_but_carry_no_audio_or_text(self):
        exc = self.refused([(0.5, 1.0), (1.0, 0.25)])
        self.assertEqual(exc.code, "invalid_intervals")
        self.assertNotIn(SECRET_SENTENCE, str(exc))
        self.assertLess(len(str(exc)), 120)

    def test_valid_ordered_touching_intervals_are_accepted_without_merging(self):
        asr = self.loaded()
        spans = [(0.5, 1.0), (1.0, 1.5), (2.0, 2.5)]  # Silero padding can make intervals touch
        result = asr.transcribe(au.silence(3), "en", spans)
        self.assertEqual(result.intervals_decoded, 3)
        self.assertEqual(len(asr._backend.calls), 3)

    def test_only_the_accepted_regions_reach_the_decoder(self):
        asr = self.loaded()
        spans = [(0.25, 0.75), (2.0, 2.5)]
        result = asr.transcribe(au.silence(3), "hi", spans)
        self.assertEqual([c["_samples"] for c in asr._backend.calls], [8000, 8000])  # 0.5 s each, not 3 s
        self.assertEqual([(s.start, s.end) for s in result.segments], [(0.25, 1.25), (2.0, 3.0)])

    def test_validation_uses_the_silero_units(self):
        from ml.runtime.asr import validate_speech_intervals
        self.assertEqual(validate_speech_intervals([(0, 1), (1, 1.5)], 32000), [(0.0, 1.0), (1.0, 1.5)])
        self.assertEqual(validate_speech_intervals([], 0), [])


class TestGatedPipeline(RootCase):
    def setUp(self):
        super().setUp()
        FakeASRBackend.instances = 0

    def pipeline(self, spans):
        self.vad_backend = FakeVADBackend(spans)
        return GatedTranscriber(SileroVAD(backend_factory=lambda: self.vad_backend), self.asr())

    def test_silence_yields_no_intervals_and_zero_decoder_calls(self):
        gated = self.pipeline([])
        result = gated.transcribe(au.silence(5), "hi")
        self.assertEqual((result.status, result.intervals_detected, result.decoder_invoked), ("no_speech", 0, False))
        self.assertTrue(result.vad_gated)
        self.assertEqual(FakeASRBackend.instances, 0)  # Whisper was never even loaded
        self.assertFalse(gated.asr.loaded)

    def test_empty_audio_returns_no_speech_without_loading_whisper(self):
        gated = self.pipeline([(0.5, 1.0)])
        result = gated.transcribe(au.silence(0), "en")
        self.assertEqual(result.status, "no_audio")
        self.assertEqual(self.vad_backend.calls, 0)
        self.assertEqual(FakeASRBackend.instances, 0)

    def test_speech_like_signal_follows_vad_then_validated_intervals_then_decoder(self):
        gated = self.pipeline([(0.5, 1.5)])
        result = gated.transcribe(au.voiced_pattern(2), "hi")
        self.assertEqual(self.vad_backend.calls, 1)
        self.assertEqual(FakeASRBackend.instances, 1)
        self.assertEqual([c["_samples"] for c in gated.asr._backend.calls], [16000])
        self.assertEqual((result.intervals_detected, result.intervals_decoded), (1, 1))
        self.assertTrue(result.vad_gated)
        st.assert_no_decision_keys(result.summary())

    def test_a_malformed_vad_output_never_reaches_whisper(self):
        gated = self.pipeline([(0.5, 1.5), (1.0, 1.8)])
        with self.assertRaises(st.RuntimeFailure) as ctx:
            gated.transcribe(au.silence(2), "hi")
        self.assertEqual(ctx.exception.code, "invalid_intervals")
        self.assertEqual(gated.asr._backend.calls, [])

    def test_unsupported_sample_rates_remain_rejected(self):
        gated = self.pipeline([(0.5, 1.0)])
        for rate in (8000, 44100):
            with self.assertRaises(st.RuntimeFailure) as ctx:
                gated.transcribe(au.silence(1), "hi", sample_rate=rate)
            self.assertEqual(ctx.exception.code, "unsupported_sample_rate")
        self.assertEqual(FakeASRBackend.instances, 0)

    def test_no_d4_score_band_routing_or_crisis_value_is_added(self):
        gated = self.pipeline([(0.5, 1.5)])
        summary = gated.transcribe(au.voiced_pattern(2), "en").summary()
        st.assert_no_decision_keys(summary)
        self.assertIsNone(re.search(r"[\"']D4[\"']\s*:", (RUNTIME / "pipeline.py").read_text(encoding="utf-8")))

    def test_unload_releases_both_stages(self):
        gated = self.pipeline([(0.5, 1.5)])
        gated.transcribe(au.voiced_pattern(2), "hi")
        backend = gated.asr._backend
        gated.unload()
        self.assertTrue(backend.closed)
        self.assertFalse(gated.asr.loaded)


class TestBenchmarkBoundary(RootCase):
    def test_ungated_decoding_is_private_and_labelled_benchmark_only(self):
        from ml.runtime.asr import _transcribe_ungated_for_benchmark
        asr = self.asr()
        asr.load()
        result = _transcribe_ungated_for_benchmark(asr, au.silence(1), "hi")
        self.assertFalse(result.vad_gated)
        self.assertTrue(result.benchmark_only)
        self.assertTrue(result.decoder_invoked)
        self.assertEqual(asr._backend.calls[-1]["_samples"], 16000)  # the whole buffer: that is the point
        self.assertNotIn("text", result.summary())

    def test_it_is_not_exported(self):
        import ml.runtime
        from ml.runtime import asr as asr_mod
        self.assertFalse(hasattr(ml.runtime, "_transcribe_ungated_for_benchmark"))
        self.assertFalse(hasattr(WhisperASR, "_transcribe_ungated_for_benchmark"))
        # a leading underscore and no __all__ keep it out of every star import
        self.assertNotIn("_transcribe_ungated_for_benchmark", getattr(asr_mod, "__all__", ()))
        self.assertTrue(callable(asr_mod._transcribe_ungated_for_benchmark))

    def test_only_the_benchmark_references_the_bypass(self):
        users = sorted(p.relative_to(ML).as_posix() for p in ML.rglob("*.py")
                       if "tests" not in p.parts and "_transcribe_ungated_for_benchmark" in p.read_text("utf-8"))
        self.assertEqual(users, ["runtime/asr.py", "runtime/benchmark.py"])
        decode_users = sorted(p.relative_to(ML).as_posix() for p in ML.rglob("*.py")
                              if "tests" not in p.parts and "._decode(" in p.read_text("utf-8"))
        self.assertEqual(decode_users, ["runtime/asr.py"])

    def test_benchmark_summaries_never_print_transcript_text(self):
        text = (RUNTIME / "benchmark.py").read_text(encoding="utf-8")
        uses = re.findall(r"[^\n]*\.text\b[^\n]*", text)
        self.assertTrue(uses)
        self.assertTrue(all("len(r.text)" in line for line in uses), uses)

    def test_normal_smoke_checks_use_the_gated_pipeline(self):
        text = (RUNTIME / "verify_models.py").read_text(encoding="utf-8")
        callers = set(re.findall(r"(\w+)\.transcribe\(", text))
        self.assertEqual(callers, {"gated"})
        self.assertNotIn("_decode(", text)


# --- VAD ------------------------------------------------------------------------------------------------


class TestVAD(unittest.TestCase):
    def setUp(self):
        self.backend = FakeVADBackend()
        self.vad = SileroVAD(backend_factory=lambda: self.backend)

    def test_sample_rate_is_validated(self):
        self.vad.load()
        for rate in (8000, 44100, 48000):
            with self.assertRaises(st.RuntimeFailure) as ctx:
                self.vad.intervals(au.silence(1), sample_rate=rate)
            self.assertEqual(ctx.exception.code, "unsupported_sample_rate")

    def test_empty_audio_returns_no_intervals_without_the_model(self):
        self.vad.load()
        result = self.vad.intervals(au.silence(0))
        self.assertEqual(result.intervals, [])
        self.assertEqual(self.backend.calls, 0)

    def test_intervals_and_unload(self):
        self.vad.load()
        result = self.vad.intervals(au.silence(2))
        self.assertEqual(result.intervals, [(0.5, 1.5)])
        self.assertEqual(result.speech_s, 1.0)
        self.vad.unload()
        with self.assertRaises(st.RuntimeFailure):
            self.vad.intervals(au.silence(1))

    def test_synthetic_signals_are_deterministic(self):
        self.assertEqual(len(au.silence(1.5)), 24000)
        self.assertEqual(au.voiced_pattern(0.5).tobytes(), au.voiced_pattern(0.5).tobytes())
        self.assertLessEqual(max(abs(x) for x in au.tone(0.1)), 0.3 + 1e-6)


# --- the model firewall ------------------------------------------------------------------------------


class TestModelFirewall(unittest.TestCase):
    APP = ("assessment.py", "dialogue", "guardrails", "svi", "nlp", "asr", "tts", "acoustics", "eval", "data")

    def test_no_application_module_imports_the_runtime(self):
        # ml/training and ml/shadow (Task 7, EXT-119) are explicit ML-only tooling that may use the
        # runtime; test_shadow_training proves no application module imports *them*.
        pattern = re.compile(r"^\s*(from|import)\s+(ml\.runtime|\.\.runtime|\.runtime)\b", re.M)
        for path in ML.rglob("*.py"):
            rel = path.relative_to(ML).as_posix()
            if rel.startswith(("runtime/", "tests/", "training/", "shadow/")):
                continue
            self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), rel)

    def test_the_runtime_imports_no_decision_or_dataset_module(self):
        pattern = re.compile(r"^\s*(from|import)\s+(ml\.|\.\.)(assessment|dialogue|guardrails|svi|nlp|eval|data|asr|"
                             r"acoustics|tts)\b", re.M)
        for path in RUNTIME.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(pattern.search(text), path.name)
            for marker in ("SAHAY_DATASETS_ROOT", "normalized/", "records.jsonl", "dreaddit", "emoinhindi"):
                self.assertFalse(marker in text, (path.name, marker))

    def test_no_untrained_classifier_or_prediction_exists(self):
        for path in RUNTIME.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in ("ForSequenceClassification", "ForTokenClassification", "num_labels", "softmax",
                           "argmax", "id2label"):
                self.assertFalse(marker in text, (path.name, marker))
            self.assertIsNone(re.search(r"\bpipeline\(\s*[\"']", text), path.name)
        self.assertIn("add_pooling_layer=False", (RUNTIME / "text_encoder.py").read_text(encoding="utf-8"))

    def test_the_forbidden_output_keys_cover_every_decision(self):
        for key in ("svi", "band", "d4", "crisis", "routing", "priority", "needs_human", "prediction", "logits"):
            self.assertIn(key, st.FORBIDDEN_OUTPUT_KEYS)
        with self.assertRaises(AssertionError):
            st.assert_no_decision_keys({"runtime": {"nested": [{"band": "High"}]}})

    def test_deterministic_evaluation_runs_with_models_absent(self):
        corpus = json.loads((ML / "eval" / "corpus" / "dev.json").read_text(encoding="utf-8"))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(config.ROOT_ENV, None)
            with checks.offline() as net:
                results = evaluate(corpus["samples"][:10])
        self.assertTrue(net["ok"], net)
        self.assertTrue(results)

    def test_the_llm_off_path_remains_complete(self):
        self.assertTrue(checks.llm_off()["completed"])

    def test_model_failure_cannot_suppress_the_crisis_pre_check(self):
        texts = [t["text"] for s in json.loads((ML / "eval" / "corpus" / "dev.json").read_text(encoding="utf-8"))
                 ["samples"] for t in s["turns"] if t["speaker"] == "victim"][:60]
        before = [crisis_check(t) for t in texts]
        enc = TextEncoder("muril", backend_factory=lambda d, c: (_ for _ in ()).throw(RuntimeError("boom")))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(config.ROOT_ENV, None)
            with self.assertRaises(st.RuntimeFailure):
                enc.load()
        after = [crisis_check(t) for t in texts]
        self.assertEqual(before, after)
        self.assertTrue(any(r["crisis"] for r in before))

    def test_model_outputs_cannot_reach_the_svi_and_d4_stays_unavailable(self):
        params = set(inspect.signature(assess).parameters)
        self.assertFalse(params & {"embeddings", "encoder", "transcript_model", "model_output", "runtime"})
        turns = [{"id": "t1", "speaker": "victim", "text": SENTENCES["en"][0]}]
        for channel, reason in (("mobile_voice", "acoustic_model_not_running"),
                                ("mobile_chat", "structurally_unavailable_on_text_channel")):
            d4 = assess(turns, True, channel=channel)["dims"]["D4"]
            self.assertIn(reason, json.dumps(d4))
        for path in RUNTIME.glob("*.py"):
            self.assertIsNone(re.search(r"[\"']D4[\"']\s*[:\]]", path.read_text(encoding="utf-8")), path.name)

    def test_no_model_path_or_runtime_type_reaches_the_product(self):
        pattern = re.compile(r"SAHAY_MODELS_ROOT|ml\.runtime|ml/runtime|muril_base_cased|whisper_small")
        offenders = []
        for base in ("backend", "frontend", "mobile", "docs/contracts"):
            root = REPO / base
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or set(path.parts) & {"node_modules", ".venv", "venv", "dist", "build",
                                                            ".expo", "__pycache__"}:
                    continue
                if path.suffix not in (".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".toml"):
                    continue
                if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                    offenders.append(path.relative_to(REPO).as_posix())
        self.assertEqual(offenders, [])

    def test_no_token_appears_in_redacted_output(self):
        self.assertEqual(st.redact("failed with hf_AbCdEfGhIjKlMnOp"), "failed with <token>")
        self.assertNotIn("Users", st.redact(r"cannot read C:\Users\someone\model.bin"))
        with mock.patch.dict(os.environ, {"HF_TOKEN": "hf_ShouldNeverAppear123"}):
            self.assertNotIn("hf_ShouldNeverAppear123", str(st.RuntimeFailure("load_failed", st.redact(
                "hf_ShouldNeverAppear123 rejected"))))

    def test_no_weight_audio_or_private_file_is_tracked_or_staged(self):
        tracked = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "ml"], cwd=REPO,
                                 capture_output=True, text=True, check=True).stdout.splitlines()
        bad = re.compile(r"\.(bin|safetensors|onnx|jit|pt|pth|ckpt|h5|msgpack|wav|mp3|flac|ogg|m4a)$", re.I)
        self.assertEqual([p for p in tracked if bad.search(p)], [])
        for path in RUNTIME.glob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"[A-Za-z]:\\\\|sih-dataset|hf_[A-Za-z0-9]{8,}", text), path.name)

    def test_benchmark_text_is_fictional_and_neutral(self):
        joined = " ".join(s for pool in SENTENCES.values() for s in pool).casefold()
        for word in ("kill", "suicide", "beat", "rape", "die", "मार", "मरना", "khatam kar doon"):
            self.assertNotIn(word, joined)
        self.assertEqual([r["crisis"] for r in map(crisis_check, (s for p in SENTENCES.values() for s in p))],
                         [False] * sum(len(p) for p in SENTENCES.values()))
        text = build_text("en", 30, lambda t: len(t.split()))
        self.assertGreaterEqual(len(text.split()), 30)


if __name__ == "__main__":
    unittest.main()
