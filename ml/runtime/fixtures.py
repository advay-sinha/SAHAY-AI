"""Fictional benchmark text. Standard library only.

Every sentence here was written for this file: everyday, neutral scenes (trains, markets,
weather, school) with invented people. None comes from a dataset, a case, a corpus or a
real conversation, and none describes distress, harm or danger. They exist to measure
tokenisation and latency, never model quality.
"""

from typing import Callable, Dict, List

LANGUAGES = ("en", "hi", "hinglish")
TARGET_TOKENS = (64, 128, 256)

SENTENCES: Dict[str, List[str]] = {
    "en": [
        "The morning train to the city was late again, so Meena bought tea at the station.",
        "Ravi's cousin opened a small bookshop near the bus stand last winter.",
        "The weather office expects light rain in the evening and a cool breeze after dinner.",
        "At the weekly market the tomatoes were cheap but the onions cost more than usual.",
        "The school library now stays open until six so students can finish their projects.",
        "Anita repaired the old bicycle herself and rode it to the post office.",
        "The neighbours planted mango saplings along the lane behind the temple.",
        "A new timetable for the ferry was pinned beside the ticket window.",
    ],
    "hi": [
        "सुबह की ट्रेन आज फिर देर से आई, इसलिए मीना ने स्टेशन पर चाय ली।",
        "रवि के चचेरे भाई ने पिछली सर्दियों में बस अड्डे के पास किताबों की छोटी दुकान खोली।",
        "मौसम विभाग ने शाम को हल्की बारिश और रात में ठंडी हवा की उम्मीद जताई है।",
        "साप्ताहिक बाज़ार में टमाटर सस्ते थे, पर प्याज़ रोज़ से महँगा था।",
        "स्कूल का पुस्तकालय अब छह बजे तक खुला रहता है ताकि बच्चे अपना काम पूरा कर सकें।",
        "अनीता ने पुरानी साइकिल ख़ुद ठीक की और उसी से डाकघर गई।",
        "पड़ोसियों ने मंदिर के पीछे वाली गली में आम के पौधे लगाए।",
        "नाव की नई समय-सारणी टिकट खिड़की के पास लगा दी गई।",
    ],
    "hinglish": [
        "Aaj subah wali train phir late thi, toh Meena ne station pe chai le li.",
        "Ravi ke cousin ne pichhli sardiyon mein bus stand ke paas chhoti si bookshop kholi.",
        "Mausam vibhag ke hisaab se shaam ko halki baarish aur raat ko thandi hawa hogi.",
        "Weekly market mein tamatar saste the par pyaaz roz se mehenga tha.",
        "School ki library ab chhe baje tak khuli rehti hai taaki bachche project khatam kar sakein.",
        "Anita ne purani cycle khud theek ki aur usi se post office gayi.",
        "Padosiyon ne mandir ke peeche wali gali mein aam ke paudhe lagaye.",
        "Ferry ka naya timetable ticket window ke paas laga diya gaya.",
    ],
}


def build_text(language: str, target_tokens: int, count_tokens: Callable[[str], int]) -> str:
    """Join sentences until ``count_tokens`` reaches ``target_tokens`` (approximately)."""
    pool = SENTENCES[language]
    parts: List[str] = []
    i = 0
    while True:
        parts.append(pool[i % len(pool)])
        i += 1
        text = " ".join(parts)
        if count_tokens(text) >= target_tokens or i > 200:
            return text
