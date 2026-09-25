"""SER backbone manifest, affect label mapping and SER audio integrity tooling (plan M12b).

No network, no model, no real audio: pointer files and "audio" here are synthetic bytes in a
temporary directory.
"""

import copy
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from ml import ser
from ml.data import ser_audio
from ml.ser import models

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent


class TestSerManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = models.load_manifest()

    def test_committed_manifest_is_valid(self):
        self.assertEqual(models.validate(self.manifest), [])
        ids = {m["logical_id"]: m["role"] for m in self.manifest["models"]}
        self.assertEqual(ids, {"emotion2vec_plus_large": "ser_primary_candidate", "wavlm_base_plus": "ser_alternate"})

    def test_pins_match_the_recorded_decisions(self):
        e2v = models.get(self.manifest, "emotion2vec_plus_large")
        self.assertEqual(e2v["revision"], "6c303ba987b86b93193de93e34bb2b077a6bedc4")
        self.assertIn({"path": "model.pt", "bytes": 1945790254,
                       "sha256": "be501a01f26fcdc7663a062dff86af839afbaef7c4de32f5e42d7e1ad2784da4"}, e2v["files"])
        wavlm = models.get(self.manifest, "wavlm_base_plus")
        self.assertEqual(wavlm["revision"], "4c66d4806a428f2e922ccfa1a962776e232d487b")
        self.assertIn("CC BY-SA 3.0", wavlm["licence"])
        decisions = (REPO / "docs" / "EXTERNAL_DECISIONS.md").read_text(encoding="utf-8")
        for pin in (e2v["revision"], wavlm["revision"]):
            self.assertIn(pin, decisions)

    def test_validation_rejects_unsafe_entries(self):
        cases = [
            lambda m: m["models"][0].update(revision="main"),
            lambda m: m["models"][0].update(gated=True),
            lambda m: m["models"][0]["files"][0].update(path="../x"),
            lambda m: m["models"][0]["files"][0].update(bytes=0),
            lambda m: m["models"][1].update(role="ser_primary_candidate"),
            lambda m: m["models"][0].pop("licence"),
            lambda m: m["models"][0]["files"][2].update(git_blob_sha1="0" * 40),
        ]
        for mutate in cases:
            bad = copy.deepcopy(self.manifest)
            mutate(bad)
            self.assertTrue(models.validate(bad))

    def test_emotion2vec_labels_map_or_abstain(self):
        e2v = models.get(self.manifest, "emotion2vec_plus_large")
        self.assertEqual(set(ser.E2V_TO_AFFECT), set(e2v["native_labels"]))
        mapped = {v for v in ser.E2V_TO_AFFECT.values() if v is not None}
        self.assertEqual(mapped, set(ser.AFFECT_CLASSES))
        for label in ("disgusted", "surprised", "other", "unknown"):
            self.assertIsNone(ser.E2V_TO_AFFECT[label], label)


class TestSerFirewall(unittest.TestCase):
    def test_no_product_code_references_ser(self):
        pattern = re.compile(r"ml\.ser\b|ml/ser\b|emotion2vec|wavlm")
        for base in ("backend", "frontend", "mobile", "docs/contracts"):
            root = REPO / base
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if any(part in ("node_modules", ".venv", "__pycache__", "dist", ".expo") for part in path.parts):
                    continue
                if path.is_file() and path.suffix in (".py", ".ts", ".tsx", ".js", ".json", ".md"):
                    self.assertIsNone(pattern.search(path.read_text(encoding="utf-8", errors="ignore")),
                                      path.relative_to(REPO).as_posix())

    def test_ser_modules_import_nothing_heavy_at_module_scope(self):
        import ast
        for path in (ML / "ser").glob("*.py"):
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    for name in names:
                        self.assertNotIn(name.split(".")[0], {"torch", "numpy", "funasr", "transformers",
                                                              "huggingface_hub", "onnxruntime"}, path.name)


def _pointer(data: bytes) -> bytes:
    return (f"version https://git-lfs.github.com/spec/v1\noid sha256:{hashlib.sha256(data).hexdigest()}\n"
            f"size {len(data)}\n").encode("ascii")


class TestCremaIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = dict(ser_audio.CREMA)
        ser_audio.CREMA.update(expected_wav=3, expected_bytes=3 * 1000)
        self.audio = {f"100{i}_TST_ANG_XX.wav": bytes([i]) * 1000 for i in range(3)}
        ptr_dir = self.root / ser_audio.CREMA["pointer_dir"]
        ptr_dir.mkdir(parents=True)
        for name, data in self.audio.items():
            (ptr_dir / name).write_bytes(_pointer(data))

    def tearDown(self):
        ser_audio.CREMA.clear()
        ser_audio.CREMA.update(self.saved)
        self.tmp.cleanup()

    def _download(self, files):
        target = self.root / ser_audio.CREMA["audio_dir"]
        target.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (target / name).write_bytes(data)

    def test_snapshot_then_verify(self):
        snap = ser_audio.snapshot_crema_pointers(self.root)
        self.assertEqual(snap["result"], "verified", snap)
        self.assertEqual(ser_audio.verify_crema(self.root)["result"], "incomplete_or_failed")
        self._download(self.audio)
        report = ser_audio.verify_crema(self.root)
        self.assertEqual(report["result"], "verified", report)
        self.assertEqual(report["verified"], 3)

    def test_verify_catches_pointer_tamper_and_extra(self):
        ser_audio.snapshot_crema_pointers(self.root)
        files = dict(self.audio)
        names = sorted(files)
        files[names[0]] = _pointer(files[names[0]])       # never pulled
        files[names[1]] = bytes([9]) * 1000               # same size, wrong content
        files["extra.wav"] = b"x" * 10
        self._download(files)
        report = ser_audio.verify_crema(self.root)
        self.assertEqual((report["still_pointer"], report["hash_mismatch"], report["unexpected_extra_files"]),
                         (1, 1, 1))
        self.assertEqual(report["result"], "incomplete_or_failed")

    def test_verify_without_snapshot_refuses(self):
        self.assertEqual(ser_audio.verify_crema(self.root)["result"], "no_pointer_manifest")

    def test_snapshot_refuses_unexpected_set(self):
        (self.root / ser_audio.CREMA["pointer_dir"] / "real_audio.wav").write_bytes(b"RIFF" + b"\0" * 2000)
        self.assertEqual(ser_audio.snapshot_crema_pointers(self.root)["result"], "unexpected_pointer_set")

    def test_reports_carry_no_names_or_paths(self):
        ser_audio.snapshot_crema_pointers(self.root)
        self._download(self.audio)
        blob = json.dumps(ser_audio.verify_crema(self.root))
        self.assertNotIn("TST", blob)
        self.assertNotIn(self.tmp.name, blob)


class TestRavdessConstants(unittest.TestCase):
    def test_pins_match_the_decision_log(self):
        decisions = (REPO / "docs" / "EXTERNAL_DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn(ser_audio.RAVDESS["md5"], decisions)
        self.assertIn("208,468,073", decisions)
        self.assertEqual(ser_audio.RAVDESS["bytes"], 208468073)
        self.assertTrue(ser_audio.RAVDESS["url"].startswith("https://zenodo.org/api/records/1188976/"))


if __name__ == "__main__":
    unittest.main()
