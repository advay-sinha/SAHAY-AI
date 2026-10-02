"""Meaning check for reworded English intents (EXT-132). Pure, standard library only.

The output validator catches unsafe content but not a changed meaning: in the first
measured trial a fluent rewording passed it while asking a different question. A
rewording is accepted only if it keeps every required concept of its intent. Each
concept is a group of acceptable stems; at least one stem of every group must appear.

English only: Hindi and Hinglish use approved text, not live rewording.
"""

import re
from typing import Dict, Optional, Tuple

from ..dialogue import intents as _intents

#: intent -> required concept groups. A stem matches whole words only; a trailing "*" marks a
#: prefix ("injur*" matches "injured"). Whole-word matching stops "fir" matching "first", "who"
#: matching "whose" and "here" matching "there" (2026-10-02 safety review).
REQUIRED: Dict[str, Tuple[Tuple[str, ...], ...]] = {
    _intents.ACKNOWLEDGE: (("thank*", "listen*", "go on", "continu*", "keep", "here", "hear*"),),
    _intents.ASK_IMMEDIATE_SAFETY: (("safe*",), ("reach*", "get to", "come to", "find you", "get near")),
    # "Does anyone need" covers family members too; "Do you need" narrows it (measured drift).
    _intents.ASK_MEDICAL_NEED: (("medical*", "doctor*", "hospital*", "treatment*", "injur*", "hurt*"),
                                ("help", "care", "need*", "attention", "treatment*"),
                                ("anyone", "anybody", "someone", "somebody", "any of you", "you or")),
    _intents.ASK_WHO_AND_WHEN: (("who",), ("when", "what time", "what day")),
    _intents.ASK_ONGOING_THREAT: (("threat*", "intimidat*", "pressur*", "harass*"),
                                  ("complain*", "report*", "speak*", "quiet", "silent", "come forward")),
    _intents.ASK_SUPPORT_NETWORK: (("someone", "anyone", "somebody", "anybody", "a person", "people"),
                                   ("with you",)),
    _intents.ASK_EXISTING_ACTION: (("complaint*", "fir", "report*", "case"),
                                   ("legal*", "lawyer*", "advocate*", "law")),
    _intents.ASK_WHAT_THEY_WANT: (("help*", "support*", "assistance"),),
}


#: Distinctive phrases per question intent. A rewording of one intent may not carry
#: another intent's anchor: that is a second request or a substituted question.
ANCHORS: Dict[str, Tuple[str, ...]] = {
    _intents.ASK_IMMEDIATE_SAFETY: ("safe*",),
    _intents.ASK_MEDICAL_NEED: ("medical*", "doctor*", "hospital*", "injur*"),
    _intents.ASK_WHO_AND_WHEN: ("who was", "who were", "who did", "who is", "when did", "when was"),
    _intents.ASK_ONGOING_THREAT: ("threat*", "intimidat*", "harass*"),
    _intents.ASK_SUPPORT_NETWORK: ("with you right now", "with you now", "someone with you",
                                   "anyone with you", "somebody with you", "anybody with you"),
    _intents.ASK_EXISTING_ACTION: ("complaint*", "fir", "lawyer*", "legal*"),
    _intents.ASK_WHAT_THEY_WANT: ("what help", "what kind of help", "what support", "what kind of support",
                                  "how can we help", "what would help", "what sort of help"),
}


def _has(norm: str, stem: str) -> bool:
    prefix = stem.endswith("*")
    word = re.escape(stem.rstrip("*"))
    return re.search(r"(?<![a-z0-9])" + word + ("" if prefix else r"(?![a-z0-9])"), norm) is not None


def _normal(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip() + " "


def keeps_meaning(text: Optional[str], intent: str) -> bool:
    """True when `text` carries every required concept of `intent` (English)."""
    groups = REQUIRED.get(intent)
    if not text or groups is None:
        return False
    norm = _normal(text)
    if not all(any(_has(norm, stem) for stem in group) for group in groups):
        return False
    if intent in ANCHORS and not any(_has(norm, a) for a in ANCHORS[intent]):
        return False
    return not any(any(_has(norm, a) for a in anchors)
                   for other, anchors in ANCHORS.items() if other != intent)
