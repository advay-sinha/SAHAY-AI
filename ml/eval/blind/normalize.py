"""Deterministic text folding used ONLY to compare a submission against the
exposed corpora. Standard library only.

This is a leakage-detection helper, not a matching layer for the pipeline. It
is deliberately separate from ``ml.guardrails.normalize``: importing that
module executes ``ml/guardrails/__init__.py``, which loads the validator and
the crisis pre-check, and the blind-corpus tooling must not load a prediction
module before freeze (see ``firewall.py``). The two implementations fold the
same things, and ``ml/tests/test_blind_corpus.py`` pins the behaviour this one
is relied on for.

Three levels, cheapest first:

  fold(text)      NFKC, casefold, zero-width characters removed, Devanagari
                  nukta dropped (U+093C), chandrabindu folded to anusvara,
                  curly quotes straightened, dashes/underscores to spaces,
                  whitespace collapsed. Punctuation is KEPT.
  compare(text)   fold(), then every punctuation and symbol character removed
                  and whitespace re-collapsed. This is the form two texts are
                  declared "the same" on, so a change of case, spacing,
                  punctuation, quote style, nukta or Unicode composition alone
                  never hides a copy.
  token_list(text) compare() split on spaces, with Devanagari digits mapped to
                  ASCII. Used for overlap ratios and shingles.

Nothing here stems, transliterates or fuzzy-matches, and no third-party
library is involved: romanised Hindi and Devanagari Hindi are different
strings to this module by design. Cross-script copying is caught by the
declared-derivation rules and by human review, not by guesswork.
"""

import re
import unicodedata
from typing import List, Set, Tuple

_ZERO_WIDTH = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF], None)
_FOLD_CHARS = {
    0x093C: None,      # Devanagari nukta: za -> ja, fa -> pha
    0x0901: "ं",  # chandrabindu -> anusvara
    0x2018: "'", 0x2019: "'", 0x201B: "'", 0x02BC: "'",
    0x201C: '"', 0x201D: '"',
    0x2013: " ", 0x2014: " ", 0x2212: " ", 0x002D: " ", 0x005F: " ",
}
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_SPACES = re.compile(r"\s+")
#: Anything that is not a letter, a mark, a digit or a space.
_PUNCT = re.compile(r"[^\w\sऀ-ॿ]|_", re.UNICODE)


def fold(text: str) -> str:
    """Case-, width- and diacritic-folded text with punctuation preserved."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).casefold()
    s = s.translate(_ZERO_WIDTH).translate(_FOLD_CHARS)
    return _SPACES.sub(" ", s).strip()


def compare(text: str) -> str:
    """The canonical comparison form: folded, punctuation-free, space-collapsed."""
    return _SPACES.sub(" ", _PUNCT.sub(" ", fold(text))).strip()


def token_list(text: str) -> List[str]:
    """Comparison-form tokens, Devanagari digits mapped to ASCII."""
    s = compare(text).translate(_DEVANAGARI_DIGITS)
    return [t for t in s.split(" ") if t]


def token_set(text: str) -> Set[str]:
    return set(token_list(text))


def overlap(a: str, b: str) -> float:
    """Jaccard overlap of the two token sets. 0.0 when either side is empty."""
    sa, sb = token_set(a), token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def shingles(text: str, n: int = 6) -> Set[Tuple[str, ...]]:
    """All contiguous n-token windows. Empty when the text is shorter than n."""
    toks = token_list(text)
    if len(toks) < n:
        return set()
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}
