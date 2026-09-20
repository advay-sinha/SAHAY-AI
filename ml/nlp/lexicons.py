"""Deterministic detection lexicons for the text channel.

Standard library only, no I/O. Hindi (Devanagari), romanised Hindi / Hinglish,
and English.

STATUS: v1 development lexicons. They are NOT clinically or linguistically
validated. They exist so the text-first vertical slice behaves deterministically
and reproducibly; every entry must be reviewed, red-teamed and extended before
any real use. Scores are severity tiers, not probabilities.

Each dimension maps to a list of (term, tier) pairs:
    tier 3  explicit, specific, severe      (base score 85)
    tier 2  explicit                        (base score 65)
    tier 1  implied / weak                  (base score 45)

D2 (crisis / self-harm) is NOT here: it comes from the synchronous crisis
pre-check in ml/guardrails, which must stay the single source of truth for it.
D4 (acute distress) is acoustic + emotional and has no text lexicon: it is
reported as unavailable rather than guessed.
"""

from typing import Dict, List, Tuple

TIER_SCORES = {3: 85.0, 2: 65.0, 1: 45.0}

#: Corroboration across turns may raise a score, but never across a tier's
#: ceiling. For D1 the tier-2 ceiling is 69: a repeated threat of FUTURE
#: violence stays below the hard-override threshold (70), which is reserved for
#: IMMINENT danger (tier 3). Repetition does not turn "they will come back"
#: into "they are outside the door".
TIER_CEILINGS = {3: 100.0, 2: 84.0, 1: 64.0}
DIMENSION_CEILINGS = {"D1": {2: 69.0, 1: 64.0}}

Lexicon = List[Tuple[str, int]]

LEXICONS: Dict[str, Lexicon] = {
    # D1 — immediate safety threat. Tier 3 is imminent presence; tier 2 is a
    # threat of violence without imminence. Imminence is what the hard
    # override (>= 70 with confidence) is for, so only tier 3 reaches it.
    "D1": [
        ("outside my house", 3), ("outside the house", 3), ("at my door", 3),
        ("at the door", 3), ("coming now", 3), ("coming tonight", 3),
        ("they are here", 3), ("with sticks", 3), ("with weapons", 3),
        ("ghar ke bahar khade", 3), ("darwaze pe", 3), ("abhi aa rahe", 3),
        ("aaj raat aayenge", 3), ("lathi le kar", 3),
        ("घर के बाहर खड़े", 3), ("दरवाज़े पर", 3), ("अभी आ रहे", 3), ("आज रात आएंगे", 3),
        ("will come back", 2), ("come back and", 2), ("kill us", 2), ("finish us", 2),
        ("burn our house", 2), ("wapas aayenge", 2), ("maar denge", 2),
        ("jaan se maar", 2), ("ghar jala", 2),
        ("फिर आएंगे", 2), ("वापस आएंगे", 2), ("जान से मार", 2), ("मार देंगे", 2), ("घर जला", 2),
    ],
    # D3 — fear, intimidation, threats.
    "D3": [
        ("threatened", 3), ("threatening", 3), ("told us not to complain", 3),
        ("withdraw the complaint", 3), ("take back the complaint", 3),
        ("dhamki", 3), ("dhamkaya", 3), ("complaint wapas", 3), ("shikayat wapas", 3),
        ("धमकी", 3), ("धमकाया", 3), ("शिकायत वापस", 3),
        ("threat", 2), ("warned us", 2), ("intimidat", 2),
        ("afraid", 1), ("scared", 1), ("fear", 1), ("dar lag", 1), ("darr", 1), ("dar hai", 1),
        ("डर", 1),
    ],
    # D5 — trauma-ASSOCIATED indicators. Phrases a person uses about their own
    # experience. Never a diagnosis, never a label applied to the person.
    "D5": [
        ("can't sleep", 2), ("cannot sleep", 2), ("nightmares", 2), ("keep remembering", 2),
        ("flashback", 2), ("neend nahi", 2), ("baar baar yaad", 2), ("sapne aate", 2),
        ("नींद नहीं", 2), ("बार-बार याद", 2), ("बार बार याद", 2),
        ("shaking", 1), ("kaanp", 1), ("काँप", 1),
    ],
    # D6 — social isolation, boycott, displacement.
    "D6": [
        ("boycott", 3), ("social boycott", 3), ("left the village", 3), ("forced to leave", 3),
        ("hukka paani band", 3), ("bahishkar", 3), ("gaon chhod", 3),
        ("बहिष्कार", 3), ("गाँव छोड़", 3), ("गांव छोड़", 3), ("हुक्का पानी बंद", 3),
        ("not allowed to use the water", 2), ("not allowed to take water", 2), ("hand pump", 2),
        ("paani nahi lene", 2), ("nal se paani", 2), ("dukaan wale saman nahi", 2),
        ("no one talks to us", 2), ("koi baat nahi karta", 2),
        ("पानी नहीं लेने", 2), ("नल से पानी", 2), ("कोई बात नहीं करता", 2),
    ],
    # D7 — medical urgency.
    "D7": [
        ("unconscious", 3), ("not breathing", 3), ("heavy bleeding", 3),
        ("behosh", 3), ("बेहोश", 3),
        ("injured", 2), ("injury", 2), ("bleeding", 2), ("fracture", 2), ("broken arm", 2),
        ("needs a doctor", 2), ("hospital", 2), ("chot", 2), ("khoon", 2), ("haath toot", 2),
        ("ilaaj", 2), ("चोट", 2), ("खून", 2), ("अस्पताल", 2), ("इलाज", 2),
        ("pain", 1), ("dard", 1), ("दर्द", 1),
    ],
    # D8 — legal urgency. Not negation-sensitive: "the FIR was NOT registered"
    # is itself a legal-urgency signal.
    "D8": [
        ("fir", 2), ("police station", 2), ("thana", 2), ("complaint", 2), ("shikayat", 2),
        ("court", 2), ("hearing", 2), ("थाना", 2), ("शिकायत", 2), ("एफ़आईआर", 2), ("अदालत", 2),
        ("police did nothing", 3), ("refused to register", 3), ("fir nahi likhi", 3),
        ("report nahi likhi", 3), ("एफ़आईआर नहीं लिखी", 3), ("रिपोर्ट नहीं लिखी", 3),
    ],
    # D9 — communication safety (cannot speak freely).
    "D9": [
        ("someone is listening", 3), ("can't talk openly", 3), ("cannot speak freely", 3),
        ("they check my phone", 3), ("koi sun raha", 3), ("khul ke nahi bol", 3),
        ("कोई सुन रहा", 3), ("खुलकर नहीं बोल", 3),
        ("can't talk now", 2), ("they are nearby", 2), ("paas mein hain", 2), ("धीरे बोल", 2),
    ],
}

#: Dimensions whose hits are cancelled by a nearby negation.
#: D8 is deliberately absent (see above). D6 terms that contain a negation
#: word ("not allowed", "paani nahi") are protected because the check skips
#: the term's own span.
NEGATION_SENSITIVE = frozenset({"D1", "D3", "D5", "D7", "D9"})

NEGATIONS_BEFORE = ("no one", "nobody", "not", "never", "didn't", "did not", "no ", "n't ")
NEGATIONS_AFTER = ("nahi", "nahin", "nahī", "नहीं", "नही")
NEGATION_WINDOW = 18  # characters

#: People / roles for structured extraction. Plain role words only.
PERSON_TERMS: Tuple[str, ...] = (
    "pradhan", "sarpanch", "village head", "neighbour", "neighbor", "landlord",
    "zamindar", "police", "shopkeeper", "dukaan wala", "maalik",
    "प्रधान", "सरपंच", "पड़ोसी", "मालिक", "पुलिस", "दुकानदार",
)

#: Relative time expressions for the incident timeline.
TIME_TERMS: Tuple[str, ...] = (
    "yesterday", "last week", "last month", "since the complaint", "two days ago",
    "kal", "pichle hafte", "pichle mahine", "do din pehle", "complaint ke baad",
    "कल", "पिछले हफ्ते", "पिछले महीने", "दो दिन पहले", "शिकायत के बाद",
)

#: Self-reports of being safe right now. Used only to detect CONFLICT with a
#: tier-3 D1 statement, never to lower a score.
SAFE_NOW_TERMS: Tuple[str, ...] = (
    "i am safe", "we are safe", "safe now", "surakshit hoon", "surakshit hain",
    "सुरक्षित हूँ", "सुरक्षित हैं",
)
