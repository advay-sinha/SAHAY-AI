"""The three pure modules must stay pure.

dialogue, guardrails and svi are imported by the backend without any ML
dependency, and manual verification runs them in seconds. This test fails if
anyone adds I/O, network access or a model import to them.
"""

import ast
import pathlib
import unittest

ML_ROOT = pathlib.Path(__file__).resolve().parents[1]
PURE_PACKAGES = ("dialogue", "guardrails", "svi")

#: Any import of these top-level modules makes the package impure.
FORBIDDEN_IMPORTS = {
    "os", "sys", "io", "pathlib", "shutil", "tempfile", "glob", "socket",
    "subprocess", "sqlite3", "asyncio", "threading", "multiprocessing",
    "requests", "httpx", "urllib", "urllib3", "aiohttp",
    "torch", "torchaudio", "numpy", "scipy", "librosa", "soundfile",
    "transformers", "sklearn", "pandas", "faster_whisper", "ctranslate2",
    "sqlalchemy", "fastapi", "pydantic", "open",
}

#: Calls that touch the filesystem or the network at call time.
FORBIDDEN_CALLS = {"open", "exec", "eval", "compile", "__import__"}


def pure_files():
    for package in PURE_PACKAGES:
        yield from sorted((ML_ROOT / package).rglob("*.py"))


class TestPurity(unittest.TestCase):
    def test_pure_packages_exist(self):
        for package in PURE_PACKAGES:
            self.assertTrue((ML_ROOT / package).is_dir(), msg=package)

    def test_no_forbidden_imports(self):
        for path in pure_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        self.assertNotIn(root, FORBIDDEN_IMPORTS, msg=f"{path.name}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.level:  # relative import inside ml/ is fine
                        continue
                    root = (node.module or "").split(".")[0]
                    self.assertNotIn(root, FORBIDDEN_IMPORTS, msg=f"{path.name}: from {node.module}")

    def test_no_filesystem_or_dynamic_calls(self):
        for path in pure_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(
                        node.func.id, FORBIDDEN_CALLS, msg=f"{path.name}: {node.func.id}()"
                    )

    def test_contract_signatures_are_present(self):
        from ml import dialogue, guardrails, svi

        self.assertTrue(callable(dialogue.next))
        self.assertTrue(callable(guardrails.validate))
        self.assertTrue(callable(svi.compute))

    def test_importing_the_pure_modules_costs_nothing_external(self):
        # A plain import must not require any third-party package.
        import importlib

        for name in ("ml.dialogue", "ml.guardrails", "ml.svi"):
            importlib.import_module(name)


class TestFixedScriptsAreStillOutstanding(unittest.TestCase):
    """S0, S9 and SX are unwritten. This test documents that and fails loudly
    if a script is marked APPROVED without a review record."""

    def test_unwritten_scripts_are_tracked(self):
        from ml.dialogue.scripts import SCRIPTS, unwritten

        outstanding = unwritten()
        self.assertTrue(outstanding, "fixed scripts became speakable; check the review record")
        for key in ("SX:hi", "SX:en"):
            self.assertIn(key, SCRIPTS)

    def test_an_approved_script_must_name_its_reviewer(self):
        from ml.dialogue.scripts import SCRIPTS

        for key, record in SCRIPTS.items():
            if record.speakable:
                self.assertTrue(record.reviewer, msg=f"{key} is speakable with no named reviewer")
                self.assertTrue(record.review_date, msg=f"{key} is speakable with no review date")


if __name__ == "__main__":
    unittest.main()
