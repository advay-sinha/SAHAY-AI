"""Text language identification for hi / en / hinglish. Deterministic, stdlib only.

A script-and-marker heuristic, not a model. It exists to feed the
`low_language_confidence` abstention rule honestly: when it cannot tell what
language a turn is in, it says so and the SVI engine abstains.
"""

import re
from typing import Dict, Iterable

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")
_WORD = re.compile(r"[A-Za-z']+")

HINGLISH_MARKERS = frozenset({
    "hai", "hain", "nahi", "nahin", "mera", "meri", "mere", "hum", "humein", "hamara",
    "hamare", "gaon", "ke", "ki", "ko", "se", "aur", "bhi", "woh", "wo", "unhone",
    "kya", "kyun", "abhi", "kal", "raha", "rahe", "rahi", "diya", "gaya", "kiya",
    "wapas", "log", "bahut", "paani", "ghar", "koi", "sab", "tha", "thi", "the",
})
ENGLISH_MARKERS = frozenset({
    "the", "and", "is", "are", "was", "were", "they", "we", "my", "our", "i",
    "to", "of", "in", "not", "have", "has", "with", "for", "that", "this",
})

LOW_CONFIDENCE = 0.60


def identify(text: str) -> Dict[str, object]:
    """Return {"lang": "hi"|"en"|"hinglish"|"unknown", "confidence": float}."""
    letters = len(_DEVANAGARI.findall(text)) + len(_LATIN.findall(text))
    if letters < 3:
        return {"lang": "unknown", "confidence": 0.0}

    deva = len(_DEVANAGARI.findall(text)) / letters
    if deva >= 0.5:
        return {"lang": "hi", "confidence": round(0.75 + 0.2 * deva, 3)}

    words = [w.lower() for w in _WORD.findall(text)]
    if not words:
        return {"lang": "unknown", "confidence": 0.2}
    hing = sum(w in HINGLISH_MARKERS for w in words) / len(words)
    eng = sum(w in ENGLISH_MARKERS for w in words) / len(words)

    if hing >= 0.12 and hing >= eng * 0.6:
        return {"lang": "hinglish", "confidence": round(min(0.9, 0.6 + hing), 3)}
    if eng >= 0.10:
        return {"lang": "en", "confidence": round(min(0.95, 0.6 + eng), 3)}
    return {"lang": "unknown", "confidence": 0.3}


def aggregate(texts: Iterable[str]) -> Dict[str, object]:
    """Language and mean confidence over several turns."""
    results = [identify(t) for t in texts]
    if not results:
        return {"lang": "unknown", "confidence": 0.0, "low": True}
    counts: Dict[str, int] = {}
    for r in results:
        counts[str(r["lang"])] = counts.get(str(r["lang"]), 0) + 1
    lang = max(sorted(counts), key=lambda k: counts[k])
    mean = sum(float(r["confidence"]) for r in results) / len(results)
    return {"lang": lang, "confidence": round(mean, 3), "low": mean < LOW_CONFIDENCE}
