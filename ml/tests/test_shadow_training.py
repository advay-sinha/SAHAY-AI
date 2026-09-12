"""Task 7 shadow classifier, fictional supervision, training schedule and local demo.

Offline, model-free and GPU-free: tiny fakes stand in for every model. No checkpoint, dataset or
network is touched.
"""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ml.eval.blind import normalize as nz
from ml.eval.predict import predict
from ml.eval.schema import DETECTOR_CATEGORIES
from ml.guardrails import crisis_check
from ml.shadow import classifier as sc, demo, model as sm
from ml.training import fictional as fic, metrics, paths, stage_a

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent
HEAVY = ("torch", "transformers", "safetensors", "numpy", "tokenizers", "faster_whisper", "ctranslate2",
         "silero_vad", "psutil", "huggingface_hub")
APP = ("assessment.py", "dialogue", "guardrails", "svi", "nlp", "asr", "tts", "acoustics", "eval", "data", "runtime")


def fake_loader(probs):
    def load(directory, device):
        return {"infer": lambda texts: [list(probs) for _ in texts]}
    return load


class ShadowRoot(unittest.TestCase):
    """A temporary training root with a fake selected checkpoint."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        ckpt = self.root / "checkpoints" / "stage-c" / "seed-13"
        (ckpt / sm.ENCODER_DIR).mkdir(parents=True)
        (ckpt / sm.HEAD_FILE).write_bytes(b"fake")
        (ckpt / sm.CONFIG_FILE).write_text("{}", encoding="utf-8")
        (self.root / "checkpoints" / "stage-c" / "SELECTED.json").write_text(
            json.dumps({"checkpoint": "checkpoints/stage-c/seed-13"}), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def shadow(self, probs=(0.9, 0.1, 0.8, 0.2, 0.1, 0.1, 0.1, 0.6), loader=None):
        return sc.ShadowClassifier(str(self.root), device="cpu", loader=loader or fake_loader(probs))


# --- fictional supervision -------------------------------------------------------------------


class TestFictionalCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = fic.generate()

    def test_the_label_order_is_the_schema_detector_order(self):
        self.assertEqual(fic.LABELS, tuple(DETECTOR_CATEGORIES))
        self.assertEqual(sm.LABELS, tuple(DETECTOR_CATEGORIES))
        self.assertEqual(len(sm.LABELS), 8)
        for r in self.records[:50]:
            self.assertEqual(list(r["labels"]), list(DETECTOR_CATEGORIES))

    def test_generation_is_deterministic(self):
        again = fic.generate()
        digest = lambda rs: hashlib.sha256(json.dumps(rs, sort_keys=True).encode()).hexdigest()  # noqa: E731
        self.assertEqual(digest(again), digest(self.records))

    def test_no_template_family_crosses_splits(self):
        self.assertEqual(fic.split_isolation_errors(self.records), [])
        splits = fic.assign_splits()
        for r in self.records:
            for key in r["templates"]:
                self.assertEqual(splits[key], r["split"])

    def test_every_split_and_language_and_phenomenon_is_present(self):
        splits = {r["split"] for r in self.records}
        self.assertEqual(splits, set(fic.SPLITS))
        self.assertEqual({r["language"] for r in self.records}, set(fic.LANGUAGES))
        phen = {p for r in self.records for p in r["phenomena"]}
        for p in ("single_turn", "multi_turn", "multi_label", "safe_control", "low_distress", "expected_abstention",
                  "negation", "quotation", "attribution", "historical", "indirect", "conditional", "misspelling",
                  "punctuation_spacing", "unicode_variant", "code_switching"):
            self.assertIn(p, phen)
        for split in fic.SPLITS:
            for name in fic.LABELS:
                self.assertTrue(any(r["labels"][name] for r in self.records if r["split"] == split), (split, name))

    def test_negated_quoted_attributed_and_historical_templates_are_negative(self):
        for key, codes, phen, _ in fic.TEMPLATES:
            if set(phen) & {"negation", "quotation", "attribution", "historical", "safe_control", "low_distress",
                            "expected_abstention"}:
                self.assertEqual(codes, "", key)

    def test_schema_consistent_co_labels(self):
        for key, codes, _, _ in fic.TEMPLATES:
            if "D" in codes:
                self.assertIn("T", codes, key)  # imminent danger is also a continuing threat

    def test_templates_carry_no_identifier_or_identity_marker(self):
        banned = re.compile(r"\d{3,}|@|https?://|www\.|\bcaste\b|\breligio|\bdalit\b|\bmuslim\b|\bhindu\b|"
                            r"\bchristian\b|\bsikh\b|जाति|धर्म", re.I)
        for key, _, _, texts in fic.TEMPLATES:
            for text in texts.values():
                self.assertIsNone(banned.search(text), key)
        for lang in fic.FILLERS.values():
            for values in lang.values():
                for v in values:
                    self.assertIsNone(banned.search(v), v)

    def test_no_procedural_or_graphic_wording(self):
        banned = re.compile(r"\b(rope|poison|pills?|overdose|hang|jump off|knife|blade|cut my|gun|bullet|"
                            r"kerosene|acid)\b", re.I)
        for key, _, _, texts in fic.TEMPLATES:
            self.assertIsNone(banned.search(texts["en"]), key)

    def test_contamination_blocks_the_whole_template_family(self):
        target = next(r for r in self.records if r["templates"] == ["c01"] and r["language"] == "en")
        index = {"scenarios": {nz.compare(target["turns"][0]["text"]): "DEV-EN-X"}, "content_hashes": {},
                 "turnsets": {}, "turns": {}, "tokens": {}, "shingles": {}, "ids": set()}
        with mock.patch.object(fic.lk, "exposed_ids", lambda index=None: set()):
            result = fic.contamination(self.records, index)
        self.assertIn("c01", result["blocked_templates"])
        self.assertFalse(any("c01" in r["templates"] for r in result["kept"]))

    def test_the_committed_bank_does_not_reproduce_exposed_fixtures(self):
        screen = fic.blocked_templates()
        self.assertTrue(set(screen["blocked_templates"]) <= {"c02", "h02", "h05", "l03", "l08"})
        kept = fic.contamination(fic.generate([t for t in fic.TEMPLATES if t[0] not in screen["blocked_templates"]]))
        self.assertEqual(kept["blocked_records"], 0)


# --- metrics and selection -------------------------------------------------------------------


class TestMetrics(unittest.TestCase):
    def test_counts_and_rates(self):
        labels = ["a", "b"]
        gold = [{"a": True, "b": False}, {"a": True, "b": True}, {"a": False, "b": False}]
        pred = [{"a": True, "b": True}, {"a": False, "b": True}, {"a": False, "b": False}]
        s = metrics.summary(gold, pred, labels)
        self.assertEqual(s["per_label"]["a"]["tp"], 1)
        self.assertEqual(s["per_label"]["a"]["fn"], 1)
        self.assertEqual(s["per_label"]["b"]["fp"], 1)
        self.assertEqual(s["per_label"]["a"]["specificity"], 1.0)
        self.assertAlmostEqual(s["hamming_loss"], 2 / 6, places=3)
        self.assertAlmostEqual(s["exact_match"], 1 / 3, places=3)

    def test_the_threshold_is_fixed(self):
        self.assertEqual(metrics.THRESHOLD, 0.5)
        self.assertEqual(sm.THRESHOLD, 0.5)
        self.assertEqual(metrics.firings([0.5, 0.49], ["a", "b"]), {"a": True, "b": False})

    def test_the_predeclared_selection_rule(self):
        def r(seed, f1, rec, loss):
            return {"seed": seed, "validation": {"macro": {"f1": f1}, "min_label_recall": rec}, "validation_loss": loss}
        ranked = sorted([r(97, 0.9, 0.8, 0.1), r(13, 0.9, 0.8, 0.1), r(42, 0.9, 0.9, 0.3), r(7, 0.8, 1.0, 0.0)],
                        key=metrics.selection_key)
        self.assertEqual([x["seed"] for x in ranked], [42, 13, 97, 7])

    def test_selection_across_runs_uses_validation_only(self):
        from ml.training import stage_c

        def result(run, seed, f1, rec, loss, test_f1):
            return {"run": run, "seed": seed, "selected_epoch": 3, "validation_loss": loss,
                    "validation": {"macro": {"f1": f1}, "min_label_recall": rec},
                    "synthetic_development_test": {"macro": {"f1": test_f1}}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            rep = root / "reports" / "stage-c"
            rep.mkdir(parents=True)
            (rep / "run1.json").write_text(json.dumps({"seeds": [result("run1", 13, 0.4, 0.0, 0.3, 0.99)]}),
                                           encoding="utf-8")
            (rep / "run2.json").write_text(json.dumps({"seeds": [result("run2", 13, 0.6, 0.1, 0.2, 0.10),
                                                                 result("run2", 42, 0.6, 0.1, 0.2, 0.50)]}),
                                           encoding="utf-8")
            selection = stage_c.select_all(root)
            pointer = json.loads((root / "checkpoints" / "stage-c" / "SELECTED.json").read_text(encoding="utf-8"))
        self.assertEqual(selection["selected"], {"run": "run2", "seed": 13, "epoch": 3})  # test F1 ignored
        self.assertEqual(pointer["checkpoint"], "checkpoints/stage-c/run2-seed-13")

    def test_no_training_or_selection_code_reads_exposed_corpora(self):
        for name in ("stage_a.py", "stage_b.py", "stage_c.py", "metrics.py", "fictional.py"):
            text = (ML / "training" / name).read_text(encoding="utf-8")
            for corpus in ("dev.json", "candidates.json", "redteam", "locked.json\"", "blind_corpus"):
                if name == "fictional.py" and corpus == "locked.json\"":
                    continue  # the generator blocks against locked.json; it never trains on or scores it
                self.assertNotIn(corpus, text, (name, corpus))
        reg = (ML / "training" / "regression.py").read_text(encoding="utf-8")
        self.assertNotIn("THRESHOLD =", reg)
        self.assertIn('FORBIDDEN = ("locked.json",)', reg)


class TestSchedule(unittest.TestCase):
    def test_continuation_is_deterministic_and_dataset_aware(self):
        rows = [{"dataset_id": "big"} for _ in range(10000)] + [{"dataset_id": "small"} for _ in range(100)]
        a = stage_a.continuation_order(rows, 2000, 0.3, 7)
        b = stage_a.continuation_order(rows, 2000, 0.3, 7)
        self.assertEqual(a["order"], b["order"])
        share_small = a["drawn"]["small"] / 2000
        self.assertGreater(share_small, 100 / 10100 * 5)  # far above its natural 1%
        self.assertLess(a["drawn"]["small"], a["drawn"]["big"])

    def test_nothing_is_discarded_to_balance(self):
        rows = [{"dataset_id": "x"} for _ in range(10)]
        order = stage_a.continuation_order(rows, 30, 0.3, 1)["order"]
        self.assertEqual(sorted(set(order)), list(range(10)))  # repeats before any row is skipped


# --- laziness and the shadow runtime ---------------------------------------------------------


class TestLaziness(unittest.TestCase):
    def test_importing_training_and_shadow_loads_nothing_heavy(self):
        mods = [f"ml.training.{p.stem}" for p in (ML / "training").glob("*.py") if p.stem != "__init__"]
        mods += [f"ml.shadow.{p.stem}" for p in (ML / "shadow").glob("*.py") if p.stem != "__init__"]
        code = ("import sys\n" + "".join(f"import {m}\n" for m in mods)
                + f"print(sorted(set({HEAVY!r}) & set(m.split('.')[0] for m in sys.modules)))")
        out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        self.assertEqual(out.stdout.strip(), "[]")

    def test_no_literal_heavy_import_statement(self):
        pattern = re.compile(r"^\s*(import|from)\s+(torch|transformers|numpy|safetensors|faster_whisper)\b", re.M)
        for pkg in ("training", "shadow"):
            for path in (ML / pkg).glob("*.py"):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), path.name)


class TestShadowClassifier(ShadowRoot):
    def test_missing_model_is_unavailable_not_zero(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(paths.TRAINING_ROOT_ENV, None)
            r = sc.ShadowClassifier(device="cpu").classify([{"speaker": "victim", "text": "hello"}])
        self.assertEqual(r.status, sc.UNAVAILABLE)
        self.assertIsNone(r.probabilities)
        self.assertIsNone(r.development_firings)
        (self.root / "checkpoints" / "stage-c" / "SELECTED.json").unlink()
        self.assertEqual(self.shadow().status().status, sc.UNAVAILABLE)

    def test_incomplete_checkpoint_is_unavailable(self):
        (self.root / "checkpoints" / "stage-c" / "seed-13" / sm.HEAD_FILE).unlink()
        self.assertEqual(self.shadow().status().status, sc.UNAVAILABLE)

    def test_probabilities_and_fixed_threshold_firings(self):
        r = self.shadow().classify([{"speaker": "victim", "text": "fictional"}])
        self.assertEqual(r.status, sc.LOADED)
        self.assertEqual(list(r.probabilities), list(sm.LABELS))
        self.assertTrue(r.development_firings["crisis_self_harm"])
        self.assertFalse(r.development_firings["immediate_danger"])
        self.assertFalse(r.calibrated)
        self.assertFalse(r.authoritative)
        self.assertIn("experimental", r.identity)

    def test_output_has_no_routing_svi_d4_or_source_label(self):
        d = self.shadow().classify([{"speaker": "victim", "text": "fictional"}]).as_dict()
        keys = set(d) | set(d["probabilities"])
        self.assertFalse(keys & sc.FORBIDDEN_KEYS)
        self.assertNotIn("source:", json.dumps(d))

    def test_inference_failure_is_isolated_and_redacted(self):
        secret = "a private sentence that must never be echoed"

        def boom(texts):
            raise RuntimeError(f"failed on {secret}")
        loader = lambda d, dev: {"infer": boom}  # noqa: E731
        r = self.shadow(loader=loader).classify([{"speaker": "victim", "text": secret}])
        self.assertEqual(r.status, sc.FAILED)
        self.assertNotIn(secret, json.dumps(r.as_dict()))

    def test_load_failure_is_a_status_not_an_exception(self):
        def bad(directory, device):
            raise OSError("cannot read")
        self.assertEqual(self.shadow(loader=bad).load().status, sc.FAILED)

    def test_only_victim_turns_are_classified(self):
        text = sm.model_text([{"speaker": "assistant", "text": "a"}, {"speaker": "victim", "text": "b  c"},
                              {"speaker": "officer", "text": "d"}, {"speaker": "victim", "text": "e"}])
        self.assertEqual(text, "b c [SEP] e")


# --- the local demonstration -----------------------------------------------------------------


class TestDemo(ShadowRoot):
    def sample_turns(self, text):
        return [{"id": "t1", "speaker": "victim", "text": text, "state": "S2"}]

    def test_the_deterministic_result_is_identical_with_or_without_the_model(self):
        turns = self.sample_turns(demo.EXAMPLES[1]["turns"][0])
        with_model = demo.side_by_side(turns, "mobile_chat", self.shadow())
        failing = demo.side_by_side(turns, "mobile_chat",
                                    self.shadow(loader=lambda d, dev: {"infer": lambda t: 1 / 0}))
        missing = demo.side_by_side(turns, "mobile_chat", sc.ShadowClassifier(str(self.root / "nope"), "cpu"))
        self.assertEqual(with_model["authoritative_deterministic"], failing["authoritative_deterministic"])
        self.assertEqual(with_model["authoritative_deterministic"], missing["authoritative_deterministic"])
        self.assertEqual(failing["experimental_shadow"]["status"], sc.FAILED)
        self.assertIsNone(missing["experimental_shadow"]["probabilities"])

    def test_model_output_cannot_change_crisis_routing_or_d4(self):
        text = demo.EXAMPLES[4]["turns"][0]
        det_alone = predict({"id": "X", "channel": "mobile_chat", "turns": self.sample_turns(text)})
        for probs in ((0.0,) * 8, (1.0,) * 8):
            out = demo.side_by_side(self.sample_turns(text), "mobile_chat", self.shadow(probs))
            det = out["authoritative_deterministic"]
            self.assertEqual(det["crisis_precheck"], det_alone["crisis_precheck"])
            self.assertEqual(det["routed_critical"], det_alone["routed_critical"])
            self.assertTrue(det["d4"].startswith("unavailable"))
        self.assertEqual(crisis_check(text), crisis_check(text))

    def test_disagreement_flags_and_the_button_only_category(self):
        out = demo.side_by_side(self.sample_turns("fictional hello"), "mobile_chat", self.shadow((1.0,) * 8))
        self.assertEqual(out["shadow_vs_deterministic"]["explicit_human_request"], "no deterministic text detector")
        self.assertIn(out["shadow_vs_deterministic"]["crisis_self_harm"], ("agrees", "disagrees"))

    def test_text_is_never_echoed(self):
        secret = "fictional marker sentence zebra quartz"
        args = argparse.Namespace(example=None, text=[secret], language="en", training_root=str(self.root))
        keys_dir = self.root / "corpora" / "external-ext119-v1"
        keys_dir.mkdir(parents=True)
        (keys_dir / "exact_keys.txt").write_text("0" * 64 + "\n", encoding="utf-8")
        out = demo.run_text(args, self.shadow())
        rendered = demo.render(out["result"], out["meta"])
        self.assertNotIn("zebra", rendered)
        self.assertIn("AUTHORITATIVE", rendered)
        self.assertIn("EXPERIMENTAL SHADOW", rendered)

    def test_external_records_are_refused_as_demo_input(self):
        text = "a record that pretends to be external"
        keys_dir = self.root / "corpora" / "external-ext119-v1"
        keys_dir.mkdir(parents=True)
        (keys_dir / "exact_keys.txt").write_text(hashlib.sha256(nz.compare(text).encode()).hexdigest() + "\n",
                                                 encoding="utf-8")
        args = argparse.Namespace(example=None, text=[text], language="en", training_root=str(self.root))
        with self.assertRaises(demo.DemoRefused):
            demo.run_text(args, self.shadow())
        args.training_root = str(self.root / "missing")
        with self.assertRaises(demo.DemoRefused):
            demo.run_text(args, self.shadow())

    def test_built_in_examples_are_fictional_and_unexposed(self):
        from ml.eval.blind import leakage as lk
        index = lk.build_index(files=tuple(lk.EXPOSED_FILES) + ("locked.json",))
        for i, ex in enumerate(demo.EXAMPLES):
            turns = [{"id": f"t{j}", "speaker": "victim", "text": t} for j, t in enumerate(ex["turns"])]
            blocks = [f for f in lk.check({"turns": turns}, index) if f["severity"] == "block"]
            self.assertEqual(blocks, [], i)

    def test_examples_command_prints_no_text(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(demo.main(["examples"]), 0)
        for ex in demo.EXAMPLES:
            for t in ex["turns"]:
                self.assertNotIn(t, buf.getvalue())

    def test_no_listener_upload_or_database(self):
        text = (ML / "shadow" / "demo.py").read_text(encoding="utf-8") + \
            (ML / "shadow" / "classifier.py").read_text(encoding="utf-8")
        for marker in ("socket", "http.server", "flask", "fastapi", "uvicorn", "requests", "urllib", "sqlite",
                       "sqlalchemy", "open(", "write_text", ".write("):
            self.assertNotIn(marker, text, marker)

    def test_voice_goes_through_the_vad_gate_only(self):
        text = (ML / "shadow" / "demo.py").read_text(encoding="utf-8")
        self.assertIn("GatedTranscriber", text)
        self.assertNotIn("_transcribe_ungated_for_benchmark", text)
        self.assertNotIn("_decode(", text)
        self.assertEqual(set(re.findall(r"(\w+)\.transcribe\(", text)), {"gated"})

    def test_voice_no_speech_skips_whisper_and_assessment(self):
        from ml.runtime import asr as asr_mod, pipeline
        fake = asr_mod.ASRResult("", "hi", "transcribe", [], 6.0, "no_speech", vad_gated=True, intervals_detected=0,
                                 intervals_decoded=0, decoder_invoked=False)
        with mock.patch.object(pipeline.GatedTranscriber, "transcribe", lambda self, s, lang: fake), \
                mock.patch.object(pipeline.GatedTranscriber, "unload", lambda self: None), \
                mock.patch.object(demo, "side_by_side") as side:
            out = demo.run_voice(argparse.Namespace(audio=None, synthetic="silence", language="hi"), self.shadow())
        side.assert_not_called()
        self.assertIsNone(out["result"])
        self.assertIn("Whisper skipped", out["meta"]["summary"])


# --- firewall --------------------------------------------------------------------------------


class TestModelCardStatus(unittest.TestCase):
    CARD = ML / "shadow" / "MODEL_CARD.md"

    def test_the_card_rejects_product_integration(self):
        card = self.CARD.read_text(encoding="utf-8")
        for field, value in (("deployment_status", "rejected_for_product_integration"),
                             ("backend_integration_allowed", "false"), ("frontend_integration_allowed", "false"),
                             ("mobile_integration_allowed", "false"), ("victim_facing_allowed", "false"),
                             ("shadow_local_demo_only", "true")):
            self.assertRegex(card, rf"\|\s*`{field}`\s*\|\s*`{value}`\s*\|", field)

    def test_the_card_states_the_limits_and_promotion_path(self):
        card = self.CARD.read_text(encoding="utf-8")
        for phrase in ("0.23 on fictional validation", "0.46 on the fictional", "substantially outperformed",
                       "must not replace, supplement or influence the crisis pre-check",
                       "no numeric promotion threshold has been approved", "richer human-reviewed fictional corpus",
                       "new training and evaluation task", "separate explicit integration decision"):
            self.assertIn(phrase, card)

    def test_the_card_holds_no_private_path_or_artefact(self):
        card = self.CARD.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]|sih-dataset|checkpoints/|run\d-seed-|\.safetensors\b", card))


class TestShadowFirewall(unittest.TestCase):
    def test_no_application_module_imports_training_or_shadow(self):
        pattern = re.compile(r"^\s*(from|import)\s+(ml\.(training|shadow)|\.\.(training|shadow)|\.(training|shadow))\b",
                             re.M)
        for path in ML.rglob("*.py"):
            rel = path.relative_to(ML).as_posix()
            if rel.startswith(("training/", "shadow/", "tests/")):
                continue
            self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), rel)

    def test_no_product_code_references_the_shadow_model(self):
        pattern = re.compile(r"ml\.shadow|ml/shadow|ml\.training|ml/training|experimental_shadow_classifier|"
                             r"SAHAY_TRAINING_ROOT")
        offenders = []
        for base in ("backend", "frontend", "mobile", "docs/contracts"):
            root = REPO / base
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or set(path.parts) & {"node_modules", ".venv", "venv", "dist", "build", ".expo",
                                                            "__pycache__"}:
                    continue
                if path.suffix in (".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".toml") and \
                        pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                    offenders.append(path.relative_to(REPO).as_posix())
        self.assertEqual(offenders, [])

    def test_the_source_label_firewall_is_unchanged(self):
        from ml.data import label_firewall as fw
        self.assertEqual(fw.AUTHORISED_MAPPINGS, ())
        with self.assertRaises(Exception):
            fw.map_to_sahay("suicide_related", "crisis_self_harm")
        for path in (ML / "training").glob("*.py"):
            self.assertNotIn("map_to_sahay", path.read_text(encoding="utf-8"), path.name)

    def test_stage_c_never_starts_from_the_stage_b_checkpoint(self):
        text = (ML / "training" / "stage_c.py").read_text(encoding="utf-8")
        self.assertIn('"stage-a", "SELECTED.json"', text)
        self.assertNotIn("stage-b", text)
        for path in (ML / "shadow").glob("*.py"):
            self.assertNotIn("stage-b", path.read_text(encoding="utf-8"), path.name)

    def test_no_machine_paths_or_tokens(self):
        for pkg in ("training", "shadow"):
            for path in (ML / pkg).glob("*.py"):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"[A-Za-z]:[\\/]+(Code|Users)[\\/]|sih-dataset|hf_[A-Za-z0-9]{8,}", text),
                                  path.name)

    def test_no_weights_or_private_records_tracked(self):
        tracked = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "ml", "docs"],
                                 cwd=REPO, capture_output=True, text=True, check=True).stdout.splitlines()
        bad = re.compile(r"\.(bin|safetensors|pt|pth|ckpt|onnx|jsonl|wav|mp3)$|exact_keys|segments", re.I)
        ledger = "ml/eval/reviews/"  # the tracked human-review ledger is JSONL by design
        self.assertEqual([p for p in tracked if bad.search(p) and not p.startswith(ledger)], [])

    def test_application_code_does_not_load_torch(self):
        code = ("import sys\nimport ml.assessment, ml.eval.predict, ml.guardrails, ml.dialogue\n"
                "print(sorted({'torch','transformers'} & set(m.split('.')[0] for m in sys.modules)))")
        out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
