"""Approved intents, licensed questions and pre-written fallbacks.

Pure module: standard library only, no I/O.

The deterministic state machine picks exactly one intent from this file. An
LLM may only rephrase the licensed question for that intent; it may never
choose the intent, invent a question, or add a second question. Every intent
carries a Hindi and an English fallback so the whole dialogue runs with
LLM_PROVIDER=mock.

REVIEW STATUS
-------------
English licensed questions are transcribed verbatim from docs/dialogue/STATES.md.
Hindi strings are DRAFT and have NOT been reviewed. `is_speakable()` refuses any
string whose review status is not APPROVED, so unreviewed text cannot reach TTS.
Clearing this TODO is a `type:dialogue` change owned by Team A / A2, due Day 3.
"""

from typing import Dict, Optional

from .states import State

APPROVED = "APPROVED"
DRAFT_UNREVIEWED = "DRAFT_UNREVIEWED"
NOT_WRITTEN = "NOT_WRITTEN"

#: Per-language review status of the intent text below.
REVIEW_STATUS: Dict[str, str] = {
    "en": DRAFT_UNREVIEWED,
    "hi": DRAFT_UNREVIEWED,
}

SUPPORTED_LANGS = ("hi", "en")
DEFAULT_LANG = "hi"


# Intent identifiers. Plain constants rather than an Enum so the backend and
# the frontend contract mirror can compare against raw strings without an
# import of this package.
ACKNOWLEDGE = "acknowledge"
ASK_IMMEDIATE_SAFETY = "ask_immediate_safety"
ASK_MEDICAL_NEED = "ask_medical_need"
ASK_WHO_AND_WHEN = "ask_who_and_when"
ASK_ONGOING_THREAT = "ask_ongoing_threat"
ASK_SUPPORT_NETWORK = "ask_support_network"
ASK_EXISTING_ACTION = "ask_existing_action"
ASK_WHAT_THEY_WANT = "ask_what_they_want"
OPENING_SCRIPT = "opening_script"
CLOSING_SCRIPT = "closing_script"
CRISIS_SCRIPT = "crisis_script"
HANDOFF_SCRIPT = "handoff_script"

#: The single intent each state licenses.
STATE_INTENT: Dict[State, str] = {
    State.S0_OPENING: OPENING_SCRIPT,
    State.S1_FREE_NARRATIVE: ACKNOWLEDGE,
    State.S2_IMMEDIATE_SAFETY: ASK_IMMEDIATE_SAFETY,
    State.S3_MEDICAL_NEED: ASK_MEDICAL_NEED,
    State.S4_WHO_AND_WHEN: ASK_WHO_AND_WHEN,
    State.S5_ONGOING_THREAT: ASK_ONGOING_THREAT,
    State.S6_SUPPORT_NETWORK: ASK_SUPPORT_NETWORK,
    State.S7_EXISTING_ACTION: ASK_EXISTING_ACTION,
    State.S8_WHAT_THEY_WANT: ASK_WHAT_THEY_WANT,
    State.S9_CLOSING: CLOSING_SCRIPT,
    State.SX_CRISIS: CRISIS_SCRIPT,
    State.SH_HUMAN_HANDOFF: HANDOFF_SCRIPT,
}

#: Licensed question per intent, per language. Verbatim from STATES.md for en.
#: An intent whose text is None must never be spoken; it has not been written.
LICENSED_QUESTION: Dict[str, Dict[str, Optional[str]]] = {
    ACKNOWLEDGE: {
        "en": None,  # S1 licenses no question. Acknowledgement only.
        "hi": None,
    },
    ASK_IMMEDIATE_SAFETY: {
        "en": "Are you safe right now — can the person who harmed you reach you?",
        "hi": "क्या आप इस समय सुरक्षित हैं — जिसने आपको नुकसान पहुँचाया, क्या वह आप तक पहुँच सकता है?",
    },
    ASK_MEDICAL_NEED: {
        "en": "Does anyone need medical help right now?",
        "hi": "क्या इस समय किसी को चिकित्सा सहायता की ज़रूरत है?",
    },
    ASK_WHO_AND_WHEN: {
        "en": "Who was involved, and when did this happen?",
        "hi": "इसमें कौन शामिल था, और यह कब हुआ?",
    },
    ASK_ONGOING_THREAT: {
        "en": "Are the threats still continuing — has anyone told you not to complain?",
        "hi": "क्या धमकियाँ अब भी जारी हैं — क्या किसी ने आपसे शिकायत न करने को कहा है?",
    },
    ASK_SUPPORT_NETWORK: {
        "en": "Is there someone with you right now?",
        "hi": "क्या इस समय कोई आपके साथ है?",
    },
    ASK_EXISTING_ACTION: {
        "en": "Has a complaint or FIR been filed — do you have legal help?",
        "hi": "क्या कोई शिकायत या एफ़आईआर दर्ज हुई है — क्या आपके पास कानूनी सहायता है?",
    },
    ASK_WHAT_THEY_WANT: {
        "en": "What help are you looking for right now?",
        "hi": "आप इस समय किस तरह की मदद चाहते हैं?",
    },
    OPENING_SCRIPT: {"en": None, "hi": None},
    CLOSING_SCRIPT: {"en": None, "hi": None},
    CRISIS_SCRIPT: {"en": None, "hi": None},
    HANDOFF_SCRIPT: {"en": None, "hi": None},
}

#: Pre-written fallback spoken when the LLM is disabled or the validator
#: rejects the generated sentence. For a question intent the fallback IS the
#: licensed question, unrephrased.
FALLBACK_TEXT: Dict[str, Dict[str, Optional[str]]] = {
    ACKNOWLEDGE: {
        "en": "Thank you for telling me. Please go on.",
        "hi": "बताने के लिए धन्यवाद। आप कहिए।",
    },
    ASK_IMMEDIATE_SAFETY: LICENSED_QUESTION[ASK_IMMEDIATE_SAFETY],
    ASK_MEDICAL_NEED: LICENSED_QUESTION[ASK_MEDICAL_NEED],
    ASK_WHO_AND_WHEN: LICENSED_QUESTION[ASK_WHO_AND_WHEN],
    ASK_ONGOING_THREAT: LICENSED_QUESTION[ASK_ONGOING_THREAT],
    ASK_SUPPORT_NETWORK: LICENSED_QUESTION[ASK_SUPPORT_NETWORK],
    ASK_EXISTING_ACTION: LICENSED_QUESTION[ASK_EXISTING_ACTION],
    ASK_WHAT_THEY_WANT: LICENSED_QUESTION[ASK_WHAT_THEY_WANT],
    # Fixed-script intents draw their text from dialogue.scripts, never from here.
    OPENING_SCRIPT: {"en": None, "hi": None},
    CLOSING_SCRIPT: {"en": None, "hi": None},
    CRISIS_SCRIPT: {"en": None, "hi": None},
    HANDOFF_SCRIPT: {"en": None, "hi": None},
}

#: Intents an LLM is permitted to rephrase. Fixed scripts are excluded
#: unconditionally.
REPHRASABLE_INTENTS = frozenset(
    {
        ACKNOWLEDGE,
        ASK_IMMEDIATE_SAFETY,
        ASK_MEDICAL_NEED,
        ASK_WHO_AND_WHEN,
        ASK_ONGOING_THREAT,
        ASK_SUPPORT_NETWORK,
        ASK_EXISTING_ACTION,
        ASK_WHAT_THEY_WANT,
    }
)


def is_speakable(lang: str) -> bool:
    """True only when the intent text for this language has passed review.

    Until Team A completes the Day 3 review this returns False, and the caller
    must refuse synthesis rather than speak unreviewed text to a victim.
    """
    return REVIEW_STATUS.get(lang) == APPROVED


def licensed_question(intent: str, lang: str) -> Optional[str]:
    return LICENSED_QUESTION.get(intent, {}).get(lang)


def fallback_text(intent: str, lang: str) -> Optional[str]:
    return FALLBACK_TEXT.get(intent, {}).get(lang)
