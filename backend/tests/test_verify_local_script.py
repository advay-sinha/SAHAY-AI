"""scripts/verify-local.ps1 runs Python checks only in the component venvs.

Standard library only. The static checks read the script as text; the
preflight check runs a copy of the script in an empty temporary repository and
is skipped when no PowerShell is available.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "verify-local.ps1"


def powershell():
    return shutil.which("pwsh") or shutil.which("powershell")


class TestInterpreterSelection(unittest.TestCase):
    def setUp(self):
        self.source = SCRIPT.read_text(encoding="utf-8")

    def test_the_component_interpreters_are_the_documented_venvs(self):
        self.assertIn('$BackendPython = Join-Path $root "backend\\.venv\\Scripts\\python.exe"', self.source)
        self.assertIn('$MlPython = Join-Path $root "ml\\.venv\\Scripts\\python.exe"', self.source)

    def test_no_check_invokes_a_bare_python(self):
        commands = re.findall(r'(?m)^\s+"(.*)"\s+\$\S+\s*$', self.source)
        self.assertTrue(commands)
        for command in commands:
            self.assertIsNone(re.search(r"(^|[\s'\"])(python|py|python3)(\.exe)?\s", command), command)
        self.assertIsNone(re.search(r"(?m)^\s*(python|py)(\.exe)?\s+-", self.source))

    def test_python_checks_use_the_matching_venv(self):
        python_checks = [c for c in re.findall(r'(?m)^\s+"(.*)"\s+\$\S+\s*$', self.source) if " -m " in c]
        self.assertEqual(len(python_checks), 5)
        for command in python_checks:
            if "ml/tests" in command:
                self.assertTrue(command.startswith("& '$MlPython' -m unittest"), command)
            else:
                self.assertTrue(command.startswith("& '$BackendPython' -m "), command)

    def test_preflight_stops_before_any_check(self):
        preflight = self.source.index("PREFLIGHT FAILED")
        self.assertLess(self.source.index("exit 2"), self.source.index('Invoke-Check "'))
        self.assertLess(preflight, self.source.index('Invoke-Check "'))
        block = self.source[self.source.index("$missing = @()"):self.source.index("exit 2")]
        self.assertIsNone(re.search(r"\$env:|DATABASE_URL|SECRET|TOKEN|Get-ChildItem\s+env:", block, re.I))


@unittest.skipUnless(powershell(), "PowerShell is not available")
class TestPreflightRun(unittest.TestCase):
    def test_missing_venvs_fail_early_without_echoing_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            for name in ("verify-local.ps1", "_node-tools.ps1"):
                shutil.copyfile(REPO / "scripts" / name, scripts / name)
            env = dict(os.environ)
            env.update({"DATABASE_URL": "postgresql://u:synthetic-secret-marker@db.invalid/app",
                        "SECRET_KEY": "synthetic-signing-marker"})
            result = subprocess.run(
                [powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(scripts / "verify-local.ps1")],
                cwd=tmp, env=env, capture_output=True, text=True, timeout=120,
            )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 2, output)
        self.assertIn("PREFLIGHT FAILED", output)
        self.assertIn("backend/.venv is missing", output)
        self.assertIn("ml/.venv is missing", output)
        for marker in ("synthetic-secret-marker", "synthetic-signing-marker", "Tier 1", "PASS", "FAIL "):
            self.assertNotIn(marker, output)


if __name__ == "__main__":
    unittest.main()
