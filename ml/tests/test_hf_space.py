"""The hosted model Space must stay identical to the laptop code it mirrors (EXT-133)."""

import ast
import unittest
from pathlib import Path

from ml.eval.schema import DETECTOR_CATEGORIES
from ml.shadow import model as shadow_model
from ml.shadow import service as shadow_service

REPO = Path(__file__).resolve().parents[2]
SPACE = REPO / "hf-space"


def _constants() -> dict:
    tree = ast.parse((SPACE / "app.py").read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return out


class TestSpaceMirrorsTheLaptopCode(unittest.TestCase):
    def test_no_text_generation_endpoint(self):
        text = (SPACE / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("AutoModelForCausalLM", text)
        self.assertNotIn('api_name="phrase"', text)
        self.assertFalse((SPACE / "sahay_prompt.py").exists())

    def test_classifier_labels_threshold_and_shown_labels_match(self):
        c = _constants()
        self.assertEqual(c["LABELS"], tuple(DETECTOR_CATEGORIES))
        self.assertEqual(c["LABELS"], shadow_model.LABELS)
        self.assertEqual(c["SHOWN_LABELS"], shadow_service.SHOWN_LABELS)
        self.assertEqual(c["THRESHOLD"], shadow_model.THRESHOLD)
        self.assertEqual(c["MAX_LEN"], shadow_model.MAX_LEN)
        self.assertEqual(c["MAX_TURNS"], shadow_service.MAX_TURNS)

    def test_no_logging_no_secret_and_key_gated(self):
        text = (SPACE / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("print(", text)
        self.assertNotIn("logging", text)
        self.assertNotRegex(text, r"hf_[A-Za-z0-9]{8,}")
        self.assertIn("hmac.compare_digest", text)
        self.assertEqual(text.count("if not authorised(key)"), 1)


if __name__ == "__main__":
    unittest.main()
