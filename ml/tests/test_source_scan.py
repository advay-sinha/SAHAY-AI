"""The shared source traversal skips environments, and nothing else.

Mutation-style evidence: the real firewall tests are re-run against a temporary
copy of the tracked ``ml/`` sources. An unmodified copy with a decoy ``.venv``
passes; the same copy with a forbidden import or a benchmark-bypass reference
injected into a real module fails.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ml.tests import source_scan, test_hardening, test_model_runtime, test_pure_modules
from ml.tests.source_scan import EXCLUDED_DIR_NAMES, ML, iter_source_files

REPO = ML.parent

DECOY = (
    "import shutil\n"
    "from ml.runtime.asr import _transcribe_ungated_for_benchmark\n"
    "value = reader._decode(chunk)\n"
)


def tracked_ml_files():
    out = subprocess.run(["git", "ls-files", "ml"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def run_case(case_class, name):
    result = unittest.TestResult()
    case_class(name).run(result)
    return result


class TestTraversal(unittest.TestCase):
    def test_environment_and_cache_directories_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in (".venv/Lib/site-packages/pip/x.py", "site-packages/y.py", "nlp/__pycache__/z.py",
                        "nlp/real.py", "real_top.py"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x = 1\n", encoding="utf-8")
            found = [p.relative_to(root).as_posix() for p in iter_source_files(root)]
        self.assertEqual(found, ["nlp/real.py", "real_top.py"])

    def test_a_root_whose_own_path_contains_an_excluded_name_is_still_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".venv" / "checkout" / "ml"
            (root / "nlp").mkdir(parents=True)
            (root / "nlp" / "real.py").write_text("x = 1\n", encoding="utf-8")
            self.assertEqual([p.name for p in iter_source_files(root)], ["real.py"])

    def test_the_real_ml_venv_is_skipped_when_present(self):
        venv = ML / ".venv"
        if not venv.is_dir():
            self.skipTest("no ml/.venv in this checkout")
        self.assertFalse(any(".venv" in p.relative_to(ML).parts for p in iter_source_files(ML)))

    def test_every_tracked_ml_source_file_is_visited(self):
        visited = {p.relative_to(REPO).as_posix() for p in iter_source_files(ML, "*")}
        missing = [rel for rel in tracked_ml_files() if rel not in visited]
        self.assertEqual(missing, [])

    def test_no_tracked_ml_path_uses_an_excluded_directory_name(self):
        for rel in tracked_ml_files():
            self.assertFalse(set(rel.split("/")[:-1]) & EXCLUDED_DIR_NAMES, rel)

    def test_the_exclusion_set_is_exactly_the_recognised_environment_names(self):
        self.assertEqual(source_scan.EXCLUDED_DIR_NAMES, frozenset({".venv", "site-packages", "__pycache__"}))


class TestFirewallMutations(unittest.TestCase):
    """The firewall tests still fail when real ml/ source is mutated."""

    CASES = (
        (test_model_runtime.TestBenchmarkBoundary, "test_only_the_benchmark_references_the_bypass",
         test_model_runtime, "ML"),
        (test_model_runtime.TestModelFirewall, "test_no_application_module_imports_the_runtime",
         test_model_runtime, "ML"),
        (test_hardening.TestInvariants, "test_no_external_corpus_network_or_model_access", test_hardening, "ML"),
        (test_pure_modules.TestPurity, "test_no_forbidden_imports", test_pure_modules, "ML_ROOT"),
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "ml"
        for rel in tracked_ml_files():
            if rel.endswith(".py") and not rel.startswith("ml/tests/"):
                target = self.root / rel[len("ml/"):]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / rel, target)
        decoy = self.root / ".venv" / "Lib" / "site-packages" / "pip" / "_vendor" / "urllib3" / "response.py"
        decoy.parent.mkdir(parents=True)
        decoy.write_text(DECOY, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def results(self):
        out = {}
        for case_class, name, module, attr in self.CASES:
            with mock.patch.object(module, attr, self.root):
                out[name] = run_case(case_class, name)
        return out

    def append(self, rel, text):
        path = self.root / rel
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def test_an_unmutated_copy_with_a_decoy_environment_passes(self):
        for name, result in self.results().items():
            self.assertTrue(result.wasSuccessful(), (name, result.failures, result.errors))

    def test_a_benchmark_bypass_reference_in_real_source_is_detected(self):
        self.append("nlp/detectors.py", "\nfrom ml.runtime.asr import _transcribe_ungated_for_benchmark\n")
        results = self.results()
        self.assertTrue(results["test_only_the_benchmark_references_the_bypass"].failures)
        self.assertTrue(results["test_no_application_module_imports_the_runtime"].failures)

    def test_a_decoder_call_in_real_source_is_detected(self):
        self.append("svi/__init__.py", "\n# value = model._decode(chunk)\n")
        self.assertTrue(self.results()["test_only_the_benchmark_references_the_bypass"].failures)

    def test_a_forbidden_import_in_real_source_is_detected(self):
        self.append("dialogue/policy.py", "\nimport shutil\n")
        results = self.results()
        self.assertTrue(results["test_no_external_corpus_network_or_model_access"].failures)
        self.assertTrue(results["test_no_forbidden_imports"].failures)


if __name__ == "__main__":
    unittest.main()
