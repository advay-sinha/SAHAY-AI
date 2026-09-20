"""Deterministic text normalisation for guardrail matching. Standard library only.

Two levels:

  fold(text)    Unicode-safe, length-changing folding that keeps punctuation:
                NFKC, casefold, zero-width characters removed, Devanagari
                nukta removed (ज़ -> ज), chandrabindu folded to anusvara
                (ँ -> ं), curly quotes straightened, dashes and underscores to
                spaces, whitespace collapsed. Used by the crisis pre-check,
                which needs punctuation for its clause scoping.

  tokens(text)  fold(), then English contractions expanded (don't -> do not,
                "dont" -> do not), Devanagari digits to ASCII, sentence
                punctuation to " | " (a clause marker patterns can refuse to
                cross), "?" kept as its own token, every other symbol removed.
                Used by the output-rule engine, whose phrase patterns match
                whole words only.

Neither function stems, guesses spellings or fuzzy-matches: every variant a
rule accepts is written into the rule itself.
"""

import re
import unicodedata

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
_FOLD_CHARS = str.maketrans({
    "़": None,      # nukta
    "ँ": "ं",  # chandrabindu -> anusvara
    "‘": "'", "’": "'", "‛": "'", "ʼ": "'",
    "“": '"', "”": '"',
    "–": " ", "—": " ", "−": " ", "-": " ", "_": " ",
})
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_SPACES = re.compile(r"\s+")

_CONTRACTIONS = (
    (re.compile(r"\bwon'?t\b"), "will not"), (re.compile(r"\bcan'?t\b"), "cannot"),
    (re.compile(r"\bshan'?t\b"), "shall not"), (re.compile(r"\bain'?t\b"), "is not"),
    (re.compile(r"\b(do|does|did|is|are|was|were|have|has|had|should|would|could|must|need)n'?t\b"),
     r"\1 not"),
    (re.compile(r"\b(i|you|we|they|he|she|it|that|there)'re\b"), r"\1 are"),
    (re.compile(r"\b(i|you|we|they|he|she|it)'ll\b"), r"\1 will"),
    (re.compile(r"\bi'm\b"), "i am"), (re.compile(r"\bim\b"), "i am"),
    (re.compile(r"\b(you|we|they)'ve\b"), r"\1 have"),
    (re.compile(r"\b(it|that|there|he|she)'s\b"), r"\1 is"),
    (re.compile(r"\byoure\b"), "you are"),
)
_CLAUSE_PUNCT = re.compile(r"[.,;:!।॥\n]+")
_QUESTION = re.compile(r"\?+")
_OTHER = re.compile(r"[^0-9a-zऀ-ॿ|? ]+")


def fold(text: str) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).casefold()
    s = s.translate(_ZERO_WIDTH).translate(_FOLD_CHARS)
    return _SPACES.sub(" ", s).strip()


def tokens(text: str) -> str:
    s = fold(text).translate(_DEVANAGARI_DIGITS)
    for pattern, repl in _CONTRACTIONS:
        s = pattern.sub(repl, s)
    s = s.replace("'", "")
    s = _CLAUSE_PUNCT.sub(" | ", s)
    s = _QUESTION.sub(" ? ", s)
    s = _OTHER.sub(" ", s)
    return " " + _SPACES.sub(" ", s).strip() + " "
