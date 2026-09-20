"""Fictional demo scenarios. No real person, place, case or account.

Every name, role and event below is invented for testing the text-first
pipeline. The wording uses Hinglish and Hindi because the MVP supports both.
It is not taken from, and must never be replaced by, a real complaint.
"""

#: A boycott after a complaint, escalating into continuing threats.
BOYCOTT_THREAT = {
    "id": "demo-boycott-threat",
    "lang": "hi",
    "channel": "mobile_chat",
    "consent": "granted",
    "turns": [
        "Complaint ke baad se gaon mein humara hukka paani band kar diya hai. "
        "Hand pump se paani nahi lene dete.",
        "Pichle hafte hum thane gaye to police ne report nahi likhi. "
        "Pradhan ke logon ne dhamki di ki complaint wapas lo.",
        "Abhi ghar pe hain, par woh bol kar gaye ki wapas aayenge aur maar denge. "
        "Bahut darr lag raha hai.",
        "Mere pita ko us din chot lagi thi, haath toot gaya. "
        "Ilaaj ke liye koi aspatal nahi le ja raha.",
        "Humein suraksha chahiye. Raat ko neend nahi aati, baar baar yaad aata hai. "
        "Abhi bhi koi sun raha hai, khul ke nahi bol sakti.",
        "कल फिर उन्होंने धमकी दी कि शिकायत वापस लो, वरना फिर आएंगे। "
        "दुकानदार भी सामान नहीं देता, कोई बात नहीं करता।",
    ],
}

#: Crisis language mid-intake. Tests the interrupt, not a story.
CRISIS = {
    "id": "demo-crisis-interrupt",
    "lang": "hi",
    "channel": "mobile_chat",
    "consent": "granted",
    "turns": [
        "Gaon mein humara bahishkar ho raha hai, koi baat nahi karta.",
        "Police ne shikayat nahi li.",
        "Ab aur nahi jee sakti, main jaan de dungi.",
        "Aap sun rahe ho?",
    ],
}

#: Consent declined: the text is kept for a person to read; no AI analysis.
CONSENT_DECLINED = {
    "id": "demo-consent-declined",
    "lang": "en",
    "channel": "mobile_chat",
    "consent": "declined",
    "turns": [
        "They threatened us after we filed the complaint.",
        "We cannot use the village water.",
        "Please have someone call me.",
    ],
}
