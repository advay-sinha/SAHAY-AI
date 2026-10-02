"""Hinglish register for approved Hindi text. Pure, standard library only.

When a person writes Hindi in Latin script, replies should match that register
(docs/dialogue/STATES.md writing rules). The reply is the approved Hindi sentence,
transliterated deterministically: the meaning cannot drift, because no model is
involved. A few common words get their everyday spelling instead of the strict
romanisation. The training-data transliterator (ml.nlp.transliterate) is reused
unchanged, so training corpora stay reproducible.
"""

import re
from typing import Dict

from ..nlp.transliterate import _DEVANAGARI_WORD, _romanise_word

#: Everyday spellings for words the strict romanisation renders awkwardly.
OVERRIDES: Dict[str, str] = {
    "धन्यवाद": "dhanyavaad",
    "लिए": "liye",
    "कहिए": "kahiye",
    "बताइए": "bataiye",
    "रहिए": "rahiye",
    "एफ़आईआर": "FIR",
    "वह": "woh",
    "इसमें": "isme",
    "यह": "yeh",
    "जरूरत": "zaroorat",
    "ज़रूरत": "zaroorat",
}

_SENTENCE_START = re.compile(r"(^|[.?!]\s+)([a-z])")


def to_hinglish_register(text: str) -> str:
    """Romanise the Devanagari words of approved text, with everyday spellings."""
    # The danda sits inside the Devanagari block, so it is replaced first or it would
    # be read as part of the preceding word.
    text = text.replace("॥", ".").replace("।", ".")
    roman = _DEVANAGARI_WORD.sub(lambda m: OVERRIDES.get(m.group(0), _romanise_word(m.group(0))), text)
    return _SENTENCE_START.sub(lambda m: m.group(1) + m.group(2).upper(), roman)
