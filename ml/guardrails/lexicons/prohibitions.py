"""Prohibited assistant output.

Standard library only, no I/O. Every prohibition in docs/dialogue/STATES.md
("Writing rules for every utterance") has an entry here and a test in
ml/tests/test_guardrails.py in both languages.
"""

from typing import Dict, Tuple

#: reason -> (english markers, hindi markers)
PROHIBITED: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "advice_legal": (
        ("you should file", "you must file", "file an fir", "go to the police",
         "you should report", "hire a lawyer", "you need a lawyer",
         "under section", "the law says"),
        ("आपको एफ़आईआर", "पुलिस के पास जाइए", "वकील कर", "धारा के तहत", "कानून कहता है"),
    ),
    "advice_medical": (
        ("you should see a doctor", "take this medicine", "go to the hospital",
         "apply ice", "you need treatment"),
        ("डॉक्टर के पास जाइए", "यह दवा ले", "अस्पताल जाइए", "इलाज करा"),
    ),
    "advice_procedural": (
        ("what you should do is", "the next step for you is", "you have to",
         "make sure you"),
        ("आपको यह करना चाहिए", "अगला कदम आपका", "आपको करना ही होगा"),
    ),
    "diagnosis": (
        ("you have trauma", "you are depressed", "this is ptsd", "you are in shock",
         "you seem traumatised", "you seem traumatized", "you are anxious"),
        ("आपको सदमा है", "आप अवसाद", "आपको ट्रॉमा"),
    ),
    "promise_outcome": (
        ("will be arrested", "you will get compensation", "we will get you justice",
         "this will be resolved", "i promise", "we guarantee", "within 24 hours",
         "the police will act"),
        ("गिरफ़्तार हो जाएगा", "मुआवज़ा मिलेगा", "न्याय दिलाएंगे", "मैं वादा",
         "गारंटी", "चौबीस घंटे में"),
    ),
    "graphic_detail_request": (
        ("describe the injury", "how many times did he hit", "what exactly did he do to you",
         "describe what happened to your body", "show me the wound"),
        ("चोट का वर्णन", "कितनी बार मारा", "शरीर के साथ क्या"),
    ),
    "asking_why": (
        ("why didn't you", "why did you not", "why didn t you", "why did you go",
         "why didn't you leave", "why did you wait"),
        ("आपने क्यों नहीं", "आप क्यों गए", "आपने इंतज़ार क्यों"),
    ),
    "blaming_or_testing": (
        ("are you sure that happened", "that does not sound right", "are you telling the truth",
         "it was your fault", "you should not have", "do you have proof"),
        ("क्या यह सच है", "आपकी ही गलती", "आपको नहीं करना चाहिए था", "क्या सबूत है"),
    ),
    "minimising_comfort": (
        ("calm down", "don't worry", "do not worry", "be strong", "stay strong",
         "i understand how you feel", "i know how you feel", "at least",
         "it could be worse", "everything will be fine", "everything will be okay"),
        ("शांत हो जाइए", "चिंता मत", "चिंता न", "मज़बूत बनिए", "हिम्मत रख",
         "मैं समझ सकता हूं आप कैसा", "कम से कम", "सब ठीक हो जाएगा"),
    ),
    "impersonating_human": (
        ("i am a person", "i am a human", "i am an officer", "speaking as a police officer",
         "i am a counsellor", "i am a counselor"),
        ("मैं एक इंसान हूं", "मैं अधिकारी हूं", "मैं पुलिस"),
    ),
}

#: A generated sentence must not exceed this. STATES.md: one sentence, plain words.
MAX_CHARS = 220

#: More than one question mark means more than one question was asked.
MAX_QUESTION_MARKS = 1
