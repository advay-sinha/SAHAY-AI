"""Devanagari -> Hinglish-style Roman transliteration. Standard library only, deterministic.

Hinglish writers do not follow a scheme like IAST or ISO 15919: they write "mera", "nahi",
"karna", "kya", "mujhe". This module approximates that register so Hindi text can be turned
into realistic romanised Hindi (Hinglish) for training data augmentation and matching:

* inherent vowel (schwa) deletion: word-final always ("डर" -> "dar"), and medially between
  a vowel-bearing syllable and a consonant + vowel ("करना" -> "karna", "रहता" -> "rahta");
* word-final long ā is written "a" ("मेरा" -> "mera"); elsewhere "aa" ("आप" -> "aap");
* long ī and ū are written "i" and "u" ("नहीं" -> "nahin", "हूँ" -> "hun");
* nukta letters take their common Hinglish values ("ज़" -> "z", "फ़" -> "f", "ड़" -> "d", as in
  "ladka", and "ढ़" -> "dh", as in "padhai").

It is a heuristic. Real people spell the same word several ways ("nahi", "nhi", "nahin"),
and this produces one of them. Its output reaches a victim only as the pinned, reviewed strings in
ml/dialogue/variants.py (HINGLISH_TEXT), never directly.
"""

import re
from typing import List, Optional, Tuple

_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    # precomposed nukta forms
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "dh", "फ़": "f", "य़": "y",
}
#: base consonant + combining nukta (U+093C) -> romanisation
_NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "d", "ढ": "dh", "फ": "f", "य": "y"}
_INDEPENDENT_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e",
}
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}
_VIRAMA = "्"
_NUKTA_SIGN = "़"
_NASALS = {"ं": "n", "ँ": "n"}
_VISARGA = "ः"
_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}
_PUNCT = {"।": ".", "॥": "."}
_DEVANAGARI_WORD = re.compile(r"[ऀ-ॿ]+")

# A unit is (kind, roman): kind "C" = consonant carrying an inherent schwa, "c" = consonant
# without one (virama or followed by a matra), "V" = vowel, "N" = nasal/visarga mark.
Unit = Tuple[str, str]


def _units(word: str) -> List[Unit]:
    units: List[Unit] = []
    i = 0
    while i < len(word):
        ch = word[i]
        nxt = word[i + 1] if i + 1 < len(word) else ""
        if ch in _CONSONANTS:
            roman = _CONSONANTS[ch]
            if nxt == _NUKTA_SIGN:
                roman = _NUKTA.get(ch, roman)
                i += 1
                nxt = word[i + 1] if i + 1 < len(word) else ""
            if nxt == _VIRAMA:
                units.append(("c", roman))
                i += 2
                continue
            if nxt in _MATRAS:
                units.append(("c", roman))
                units.append(("V", _MATRAS[nxt]))
                i += 2
                continue
            units.append(("C", roman))
        elif ch in _INDEPENDENT_VOWELS:
            units.append(("V", _INDEPENDENT_VOWELS[ch]))
        elif ch in _NASALS:
            units.append(("N", _NASALS[ch]))
        elif ch == _VISARGA:
            units.append(("N", "h"))
        elif ch in _DIGITS:
            units.append(("V", _DIGITS[ch]))
        elif ch in _PUNCT:
            units.append(("V", _PUNCT[ch]))
        # anything else (stray matra, nukta, zero-width joiners) is dropped
        i += 1
    return units


def _is_last(units: List[Unit], k: int) -> bool:
    """True if nothing but nasal marks follows position k."""
    return all(u[0] == "N" for u in units[k + 1:])


def _has_vowel_after(units: List[Unit], k: int) -> bool:
    """True if the consonant at k+1 is followed by a pronounced vowel.

    A consonant carrying its own schwa counts only if that schwa survives, which a word-final
    schwa never does ("कमल" keeps the vowel after m: "kamal", not "kaml").
    """
    if k + 1 >= len(units):
        return False
    kind = units[k + 1][0]
    if kind == "C":
        return not _is_last(units, k + 1)
    if kind == "c":
        return k + 2 < len(units) and units[k + 2][0] == "V"
    return False


def _romanise_word(word: str) -> str:
    units = _units(word)
    out: List[str] = []
    for k, (kind, roman) in enumerate(units):
        if kind != "C":
            if kind == "V" and roman == "aa" and k == len(units) - 1:
                out.append("a")  # word-final long ā: "mera", "tha", "kya"
            else:
                out.append(roman)
            continue
        out.append(roman)
        if _is_last(units, k):
            if len(units) == 1:
                out.append("a")           # a one-letter word such as "न" -> "na"
            continue                      # word-final schwa deleted: "dar", "ghar"
        previous_has_vowel = k > 0 and units[k - 1][0] in ("C", "V")
        if previous_has_vowel and _has_vowel_after(units, k):
            continue                      # medial schwa deletion: "karna", "rahta"
        out.append("a")
    return "".join(out)


def to_hinglish(text: str) -> str:
    """Romanise every Devanagari word in ``text``; everything else is left unchanged."""
    return _DEVANAGARI_WORD.sub(lambda m: _romanise_word(m.group(0)), text)


def devanagari_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "ऀ" <= c <= "ॿ") / len(letters)


def maybe_hinglish(text: str, min_share: float = 0.5) -> Optional[str]:
    """The romanised text, or None when the input is not mostly Devanagari."""
    return to_hinglish(text) if devanagari_share(text) >= min_share else None
