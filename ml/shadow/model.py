"""Shadow-network definition shared by Stage C training and the runtime loader.

Torch and Transformers are imported only inside the functions. The network is an encoder
(``BertModel`` without a pooler) followed by attention-masked mean pooling, dropout and one linear
layer with an independent logit per label (sigmoid-compatible; trained with BCE-with-logits).
There is no routing, SVI, D4, diagnosis or generative head.
"""

import importlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from ..eval.schema import DETECTOR_CATEGORIES

MODEL_ID = "experimental_shadow_classifier"
LABELS = tuple(DETECTOR_CATEGORIES)
MAX_LEN = 128
THRESHOLD = 0.5
CONFIG_FILE = "shadow_config.json"
HEAD_FILE = "head.safetensors"
ENCODER_DIR = "encoder"
IDENTITY = ("experimental shadow output: development-only, uncalibrated, not clinically validated, not "
            "independently evaluated, never authoritative")


def model_text(turns: Sequence[Mapping[str, Any]], sep: str = " [SEP] ") -> str:
    """The shadow input: victim turns only, in order (what the deterministic pipeline scores)."""
    return sep.join(" ".join(str(t.get("text", "")).split()) for t in turns
                    if t.get("speaker", "victim") == "victim" and str(t.get("text", "")).strip())


def build_network(encoder: Any, n_labels: int = len(LABELS), dropout: float = 0.1) -> Any:
    t = importlib.import_module("torch")

    class ShadowNet(t.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoder = encoder
            self.dropout = t.nn.Dropout(dropout)
            self.head = t.nn.Linear(encoder.config.hidden_size, n_labels)

        def forward(self, input_ids: Any, attention_mask: Any) -> Any:
            hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
            return self.head(self.dropout(pooled))

    return ShadowNet()


def load_encoder(directory: Path) -> Any:
    tf = importlib.import_module("transformers")
    tf.logging.set_verbosity_error()
    tf.logging.disable_progress_bar()
    return tf.AutoModel.from_pretrained(str(directory), local_files_only=True, add_pooling_layer=False)


def save(net: Any, tokenizer: Any, target: Path, config: Mapping[str, Any]) -> Dict[str, str]:
    """Encoder (safetensors) + tokenizer + head (safetensors) + config, written into ``target``."""
    st = importlib.import_module("safetensors.torch")
    target.mkdir(parents=True, exist_ok=True)
    net.encoder.save_pretrained(str(target / ENCODER_DIR), safe_serialization=True)
    tokenizer.save_pretrained(str(target / ENCODER_DIR))
    st.save_file({k: v.detach().cpu().contiguous() for k, v in net.head.state_dict().items()}, str(target / HEAD_FILE))
    (target / CONFIG_FILE).write_text(json.dumps({**config, "model_id": MODEL_ID, "labels": list(LABELS),
                                                  "threshold": THRESHOLD, "max_len": MAX_LEN,
                                                  "pooling": "attention-masked mean", "calibrated": False,
                                                  "authoritative": False, "identity": IDENTITY},
                                                 indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {}


def load(directory: Path, device: str = "cpu") -> Dict[str, Any]:
    t = importlib.import_module("torch")
    st = importlib.import_module("safetensors.torch")
    tf = importlib.import_module("transformers")
    config = json.loads((directory / CONFIG_FILE).read_text(encoding="utf-8"))
    if config.get("model_id") != MODEL_ID or tuple(config.get("labels", ())) != LABELS:
        raise ValueError("checkpoint identity or label order does not match this code")
    encoder = load_encoder(directory / ENCODER_DIR)
    net = build_network(encoder, len(LABELS))
    net.head.load_state_dict(st.load_file(str(directory / HEAD_FILE)))
    net.to(device).eval()
    tokenizer = tf.AutoTokenizer.from_pretrained(str(directory / ENCODER_DIR), local_files_only=True)
    return {"net": net, "tokenizer": tokenizer, "config": config, "torch": t}
