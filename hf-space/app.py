"""SAHAY-AI model Space (EXT-133, PC-14): advisory signals for officers.

Runs on Hugging Face ZeroGPU. The endpoint refuses to answer without the shared key
(Space secret SAHAY_SPACE_KEY), so a public Space cannot be used by anyone else. Inputs and
outputs are never logged. The SAHAY backend treats every reply as untrusted and rebuilds it
from an allowlist. There is no text-generation endpoint: after the 2026-10-02 dialogue
safety review no model writes text to a victim at runtime.

The network and constants below mirror ml/shadow/model.py and ml/shadow/service.py
(ml/tests/test_hf_space.py checks them).
"""

import hmac
import json
import os

import gradio as gr
import spaces
import torch
from huggingface_hub import snapshot_download
from safetensors.torch import load_file
from transformers import AutoModel, AutoTokenizer

LABELS = (
    "crisis_self_harm",
    "immediate_danger",
    "continuing_threat",
    "medical_urgency",
    "isolation_boycott_displacement",
    "legal_urgency",
    "communication_safety_coercion",
    "explicit_human_request",
)
SHOWN_LABELS = ("crisis_self_harm", "communication_safety_coercion", "legal_urgency")
THRESHOLD = 0.5
MAX_LEN = 128
MAX_TURNS = 40
CHECKPOINT_STATUS = "rejected_for_product_integration"

KEY = os.environ.get("SAHAY_SPACE_KEY", "")
SIGNALS_REPO = os.environ.get("SAHAY_SIGNALS_REPO", "")

# --- the model loads at module level, as ZeroGPU requires ----------------------------------------


class ShadowNet(torch.nn.Module):
    """Encoder + attention-masked mean pooling + linear head (mirrors ml/shadow/model.py)."""

    def __init__(self, encoder, n_labels: int, dropout: float = 0.1) -> None:
        super().__init__()
        self.encoder = encoder
        self.dropout = torch.nn.Dropout(dropout)
        self.head = torch.nn.Linear(encoder.config.hidden_size, n_labels)

    def forward(self, input_ids, attention_mask):
        hidden = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
        pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
        return self.head(self.dropout(pooled))


signal_net = signal_tokenizer = None
if SIGNALS_REPO:
    folder = snapshot_download(SIGNALS_REPO, token=os.environ.get("HF_TOKEN") or None)
    with open(os.path.join(folder, "shadow_config.json"), encoding="utf-8") as f:
        config = json.load(f)
    if tuple(config.get("labels", ())) != LABELS:
        raise ValueError("checkpoint label order does not match this Space")
    encoder = AutoModel.from_pretrained(os.path.join(folder, "encoder"), add_pooling_layer=False)
    signal_net = ShadowNet(encoder, len(LABELS))
    signal_net.head.load_state_dict(load_file(os.path.join(folder, "head.safetensors")))
    signal_net.to("cuda").eval()
    signal_tokenizer = AutoTokenizer.from_pretrained(os.path.join(folder, "encoder"))


def authorised(key) -> bool:
    return bool(KEY) and isinstance(key, str) and hmac.compare_digest(key.encode(), KEY.encode())


# --- advisory signals --------------------------------------------------------------------------------


@spaces.GPU(duration=15)
def _probabilities(text: str):
    enc = signal_tokenizer([text], max_length=MAX_LEN, truncation=True, padding=True, return_tensors="pt").to("cuda")
    with torch.inference_mode():
        logits = signal_net(enc["input_ids"], enc["attention_mask"])[0]
    return torch.sigmoid(logits.float()).tolist()


def signals(texts, key) -> dict:
    """PC-14 payload: shown labels only, advisory, uncalibrated."""
    empty = {"status": "unavailable", "checkpoint_status": CHECKPOINT_STATUS, "labels": {}}
    if not authorised(key) or signal_net is None:
        return empty
    if not isinstance(texts, list) or not texts or len(texts) > MAX_TURNS or not all(isinstance(t, str) for t in texts):
        return empty
    text = " [SEP] ".join(" ".join(t.split()) for t in texts if t.strip())
    if not text:
        return empty
    try:
        probs = _probabilities(text)
    except Exception:
        return {**empty, "status": "failed"}
    return {"status": "loaded", "checkpoint_status": CHECKPOINT_STATUS,
            "labels": {name: {"probability": round(p, 4), "fired": p >= THRESHOLD}
                       for name, p in zip(LABELS, probs) if name in SHOWN_LABELS}}


with gr.Blocks(title="SAHAY-AI models") as demo:
    gr.Markdown("SAHAY-AI model service (prototype, fictional data only). API use requires the shared key.")
    with gr.Row():
        key = gr.Textbox(label="Key", type="password")
    texts = gr.JSON(label="Victim turns (list of strings)")
    reading = gr.JSON(label="Advisory signal")
    gr.Button("Signals").click(signals, [texts, key], reading, api_name="signals")

demo.queue(max_size=16).launch()
