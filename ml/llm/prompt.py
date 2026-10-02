"""Prompt construction and output cleaning for guardrailed phrasing (EXT-132).

Pure module: standard library only, no I/O, no model loading.

The language model only rewords the one sentence the state machine already
chose. It never sees what the person wrote: it receives the approved source
sentence, the language, and a register label derived deterministically from
the person's last message. Nothing a person types can steer it into a
different question. Every output still passes guardrails.validate, and any
failure falls back to the pre-written sentence.
"""

import re
import unicodedata
from typing import Dict, List, Optional

PROMPT_VERSION = "phrase-v2"
REGISTERS = ("hi", "en", "hinglish")
MAX_OUTPUT_CHARS = 220

_REGISTER_INSTRUCTION: Dict[str, str] = {
    "en": "Write in plain, simple English.",
    "hi": "Write in simple, everyday Hindi in Devanagari script, addressing the person as आप.",
    "hinglish": (
        "Write in romanised Hindi (Hinglish) in Latin script, the way people type Hindi on a "
        "phone, addressing the person as aap."
    ),
}

_SYSTEM = (
    "You reword one sentence for a helpline intake assistant. The listener may be a survivor of "
    "caste violence, sexual violence or bereavement, and may be in distress.\n"
    "Rules:\n"
    "- Output exactly one sentence and nothing else: no greeting, no quotes, no explanation.\n"
    "- Keep exactly the same meaning as the source sentence. Do not add or remove any request.\n"
    "- If the source is a question, output one question with exactly one question mark. If the "
    "source asks two things, keep both in that one sentence, joined with 'and' or a dash. If the "
    "source is not a question, output no question.\n"
    "- Plain, gentle, respectful words. Short.\n"
    "- Never give advice, promises, opinions, diagnosis or comfort phrases such as "
    "'don't worry' or 'stay strong'.\n"
    "- Never ask why, and never ask for detail about an injury, an assault or a death.\n"
    "- Never mention scores, risk, assessment or that anything was detected.\n"
    "- Never claim to be a person."
)


def register_for(lang: str, identified: Optional[str]) -> str:
    """The register to write in, from the session language and a deterministic language id."""
    if identified == "hinglish":
        return "hinglish"
    return lang if lang in ("hi", "en") else "hi"


def build_messages(source: str, register: str) -> List[Dict[str, str]]:
    """Chat messages for one rewording. `source` is approved text, never user text."""
    if register not in REGISTERS:
        raise ValueError("unknown register")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("empty source")
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": (
            f"{_REGISTER_INSTRUCTION[register]}\n"
            f"Source sentence: {source.strip()}\n"
            "Reworded sentence:"
        )},
    ]


_QUOTES = "\"'“”‘’«»`"
_LABEL = re.compile(r"^(reworded sentence|sentence|answer|output)\s*:\s*", re.IGNORECASE)


def clean_output(raw: Optional[str]) -> Optional[str]:
    """First non-empty line, labels and wrapping quotes removed; None when unusable."""
    if not isinstance(raw, str):
        return None
    text = unicodedata.normalize("NFC", raw).strip()
    for line in text.splitlines():
        line = _LABEL.sub("", line.strip()).strip().strip(_QUOTES).strip()
        if line:
            line = re.sub(r"\s+", " ", line)
            return line if len(line) <= MAX_OUTPUT_CHARS else None
    return None
