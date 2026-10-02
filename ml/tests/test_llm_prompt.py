"""Pure parts of guardrailed phrasing (EXT-132): prompt, output cleaning, resharding."""

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from ml.llm import prompt
from ml.llm.reshard import read_header, reshard


class TestPrompt(unittest.TestCase):
    def test_register_follows_the_deterministic_language_id(self):
        self.assertEqual(prompt.register_for("hi", "hinglish"), "hinglish")
        self.assertEqual(prompt.register_for("hi", "hi"), "hi")
        self.assertEqual(prompt.register_for("en", "unknown"), "en")
        self.assertEqual(prompt.register_for("ta", None), "hi")

    def test_messages_carry_only_the_approved_source(self):
        messages = prompt.build_messages("Is there someone with you right now?", "en")
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("Is there someone with you right now?", messages[1]["content"])
        with self.assertRaises(ValueError):
            prompt.build_messages("x", "fr")
        with self.assertRaises(ValueError):
            prompt.build_messages("  ", "en")

    def test_clean_output_takes_one_line_without_labels_or_quotes(self):
        self.assertEqual(prompt.clean_output('Reworded sentence: "Is anyone with you now?"\nExtra'),
                         "Is anyone with you now?")
        self.assertEqual(prompt.clean_output("  \n  Kya aapke saath koi hai?  "), "Kya aapke saath koi hai?")
        self.assertIsNone(prompt.clean_output(""))
        self.assertIsNone(prompt.clean_output(None))
        self.assertIsNone(prompt.clean_output("x" * (prompt.MAX_OUTPUT_CHARS + 1)))


def _write_safetensors(path: Path, tensors):
    header, blob, offset = {}, b"", 0
    for name, data in tensors:
        header[name] = {"dtype": "U8", "shape": [len(data)], "data_offsets": [offset, offset + len(data)]}
        blob += data
        offset += len(data)
    raw = json.dumps(header).encode()
    raw += b" " * (-len(raw) % 8)
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + blob)


class TestReshard(unittest.TestCase):
    def test_tensors_are_copied_byte_for_byte_into_small_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp, "src"), Path(tmp, "dst")
            src.mkdir()
            tensors = [(f"t{i}", bytes([i]) * (300_000 + i)) for i in range(8)]
            _write_safetensors(src / "model-00001-of-00001.safetensors", tensors)
            (src / "config.json").write_text("{}")
            result = reshard(src, dst, max_mb=1)
            self.assertTrue(result["verified"])
            self.assertGreater(result["shards"], 1)
            self.assertTrue((dst / "config.json").exists())
            index = json.loads((dst / "model.safetensors.index.json").read_text())
            found = {}
            for shard in set(index["weight_map"].values()):
                base, header = read_header(dst / shard)
                data = (dst / shard).read_bytes()
                for name, meta in header.items():
                    if name != "__metadata__":
                        a, b = meta["data_offsets"]
                        found[name] = hashlib.sha256(data[base + a:base + b]).hexdigest()
            self.assertEqual(found, {n: hashlib.sha256(d).hexdigest() for n, d in tensors})


if __name__ == "__main__":
    unittest.main()
