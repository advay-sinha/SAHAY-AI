"""Crisis / self-harm lexicon for the synchronous pre-check.

Standard library only, no I/O. Recall is deliberately favoured over precision:
a false positive routes a person to a human, a false negative does not.

STATUS: v1 seed list. Expansion and the negation/quotation rules must be
red-teamed by the dialogue-safety-reviewer before the Day 8 gate, in both
languages, and every entry logged in the guardrail red-team table.
"""

from typing import Tuple

#: Direct first-person crisis expressions.
CRISIS_EN: Tuple[str, ...] = (
    "kill myself",
    "killing myself",
    "end my life",
    "ending my life",
    "take my own life",
    "want to die",
    "wish i was dead",
    "wish i were dead",
    "better off dead",
    "no reason to live",
    "nothing left to live for",
    "cannot go on",
    "can't go on",
    "hang myself",
    "jump in front of",
    "hurt myself",
    "harm myself",
    "suicide",
    "suicidal",
    "poison myself",
    "burn myself",
)

CRISIS_HI: Tuple[str, ...] = (
    "आत्महत्या",
    "खुदकुशी",
    "जान दे दूंगा",
    "जान दे दूँगी",
    "मर जाऊंगा",
    "मर जाऊँगी",
    "मरना चाहती हूं",
    "मरना चाहता हूं",
    "जीना नहीं चाहती",
    "जीना नहीं चाहता",
    "जहर खा",
    "ज़हर खा",
    "फांसी लगा",
    "फाँसी लगा",
    "खुद को खत्म",
    "अब और नहीं जी",
)

#: Romanised Hindi / Hinglish, since ASR output is frequently romanised.
CRISIS_HINGLISH: Tuple[str, ...] = (
    "atmahatya",
    "khudkushi",
    "jaan de dunga",
    "jaan de dungi",
    "mar jaunga",
    "mar jaungi",
    "jeena nahi chahti",
    "jeena nahi chahta",
    "zeher kha",
    "jeher kha",
    "phansi laga",
    "fansi laga",
)

#: Tokens that negate a nearby crisis phrase ("I would never kill myself").
#: Only explicit negations. Bare "no" and "na" are deliberately absent: they
#: matched "there is no point" and suppressed a genuine first-person crisis.
NEGATIONS_EN: Tuple[str, ...] = (
    "never",
    "would never",
    "will never",
    "wouldn't",
    "would not",
    "won't",
    "will not",
    "don't want to",
    "do not want to",
    "didn't",
    "did not",
    "not going to",
)

NEGATIONS_HI: Tuple[str, ...] = ("कभी नहीं", "नहीं करूंगी", "नहीं करूंगा", "kabhi nahi", "nahi karungi", "nahi karunga")

#: Tokens indicating the phrase is being reported as someone else's speech.
#: These are recorded as context on the match. They deliberately do NOT
#: suppress the crisis flag: "he told me to kill myself" is still a crisis.
ATTRIBUTION_EN: Tuple[str, ...] = (
    "he said",
    "she said",
    "they said",
    "they told me",
    "he told me",
    "she told me",
    "he threatened",
    "she threatened",
    "they threatened",
)

ATTRIBUTION_HI: Tuple[str, ...] = (
    "उसने कहा",
    "उन्होंने कहा",
    "उसने धमकी",
    "usne kaha",
    "unhone kaha",
    "usne dhamki",
)

#: How many characters either side of a match are scanned for a negation or
#: an attribution cue.
CONTEXT_WINDOW = 40

#: Explicit, bounded variants of phrases ALREADY in the lists above (added
#: 2026-09-11, safety-hardening phase, pending the type:dialogue review).
#: Each is a high-confidence misspelling, a common transliteration, or the
#: Hindi/Hinglish counterpart of an existing English entry. No fuzzy matching:
#: a variant that is not written here does not match.
#: (term, lang, reason)
CRISIS_VARIANTS: Tuple[Tuple[str, str, str], ...] = (
    ("kil myself", "en", "misspelling of 'kill myself' (CAND-EN-019 regression)"),
    ("kill my self", "en", "spacing variant of 'kill myself'"),
    ("kil my self", "en", "misspelling + spacing variant of 'kill myself'"),
    ("killmyself", "en", "spacing variant of 'kill myself'"),
    ("hurt my self", "en", "spacing variant of 'hurt myself'"),
    ("harm my self", "en", "spacing variant of 'harm myself'"),
    ("sucide", "en", "misspelling of 'suicide'"),
    ("suicde", "en", "misspelling of 'suicide'"),
    ("suiside", "en", "misspelling of 'suicide'"),
    ("sucidal", "en", "misspelling of 'suicidal'"),
    ("खुद को नुकसान पहुंचा", "hi", "Hindi counterpart of 'harm/hurt myself' (CAND-HI-003 regression)"),
    ("खुद को चोट पहुंचा", "hi", "Hindi counterpart of 'hurt myself'"),
    ("atmhatya", "hinglish", "transliteration of 'atmahatya' (CAND-HG-003 regression)"),
    ("aatmhatya", "hinglish", "transliteration of 'atmahatya'"),
    ("aatmahatya", "hinglish", "transliteration of 'atmahatya'"),
    ("khudkhushi", "hinglish", "transliteration of 'khudkushi'"),
    ("khud khushi", "hinglish", "transliteration of 'khudkushi'"),
    ("khud kushi", "hinglish", "spacing variant of 'khudkushi'"),
    ("jaan de doongi", "hinglish", "transliteration of 'jaan de dungi'"),
    ("jaan de doonga", "hinglish", "transliteration of 'jaan de dunga'"),
    ("jan de dungi", "hinglish", "transliteration of 'jaan de dungi'"),
    ("jan de dunga", "hinglish", "transliteration of 'jaan de dunga'"),
    ("mar jaaungi", "hinglish", "transliteration of 'mar jaungi'"),
    ("mar jaaunga", "hinglish", "transliteration of 'mar jaunga'"),
    ("zahar kha", "hinglish", "transliteration of 'zeher kha'"),
    ("jahar kha", "hinglish", "transliteration of 'zeher kha'"),
    ("phaansi laga", "hinglish", "transliteration of 'phansi laga'"),
    ("faansi laga", "hinglish", "transliteration of 'fansi laga'"),
    ("khud ko nuksan pahuncha", "hinglish", "Hinglish counterpart of 'harm myself'"),
    ("khud ko nuksaan pahuncha", "hinglish", "Hinglish counterpart of 'harm myself'"),
)
