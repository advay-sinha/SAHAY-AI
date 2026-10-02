"""Reviewed alternative wordings: English variants and the Hinglish register. Pure, stdlib only.

After the 2026-10-02 dialogue safety review, no model writes free text to a victim at runtime:
a lexicon cannot rule out what a model adds (74 of 79 adversarial rewordings passed the
validator and the meaning check). Variety comes from this file instead.

- English variants were generated offline by Qwen3-4B-Instruct-2507 (prompt phrase-v2),
  kept only if they passed guardrails.validate and ml.llm.meaning.keeps_meaning, and are
  spoken only once the project lead approves them (VARIANT_REVIEW).
- Hinglish strings are the approved Hindi sentences, transliterated by
  ml.dialogue.hinglish.to_hinglish_register and pinned here, so a change to the
  transliterator can never change what is said without a new review (HINGLISH_REVIEW).

Everything here is still validated at runtime before it is spoken.
"""

import random
from typing import Dict, List, Optional

from . import intents as _intents

APPROVED = _intents.APPROVED
DRAFT_UNREVIEWED = _intents.DRAFT_UNREVIEWED

#: intent -> English variants (the approved sentence itself is always a candidate too).
#: Generated 2026-10-02 (16 samples per intent); everything rejected by the checks was dropped,
#: and "not to speak up" was dropped as drift by the safety review. Qwen added little variety:
#: most intents produced only the approved sentence or a rejected rewording.
EN_VARIANTS: Dict[str, List[str]] = {
    _intents.ASK_SUPPORT_NETWORK: ["Do you have someone with you right now?"],
    _intents.ASK_WHAT_THEY_WANT: [
        "What kind of help would you like right now?",
        "What kind of help do you need right now?",
    ],
}

VARIANT_REVIEW: Dict[str, str] = {"status": APPROVED, "reviewer": "advay-sinha", "review_date": "2026-10-02"}

#: intent -> the approved Hindi sentence in Latin script, for people who write Hindi that way.
HINGLISH_TEXT: Dict[str, str] = {
    _intents.ACKNOWLEDGE: "Bataane ke liye dhanyavaad. Aap kahiye.",
    _intents.ASK_EXISTING_ACTION:
        "Kya koi shikaayat ya FIR darj hui hai — kya aapke paas kaanuni sahaayta hai?",
    _intents.ASK_IMMEDIATE_SAFETY:
        "Kya aap is samay surakshit hain — jisne aapko nuksaan pahunchaaya, kya woh aap tak pahunch sakta hai?",
    _intents.ASK_MEDICAL_NEED: "Kya is samay kisi ko chikitsa sahaayta ki zaroorat hai?",
    _intents.ASK_ONGOING_THREAT:
        "Kya dhamkiyaan ab bhi jaari hain — kya kisi ne aapse shikaayat na karne ko kaha hai?",
    _intents.ASK_SUPPORT_NETWORK: "Kya is samay koi aapke saath hai?",
    _intents.ASK_WHAT_THEY_WANT: "Aap is samay kis tarah ki madad chaahte hain?",
    _intents.ASK_WHO_AND_WHEN: "Isme kaun shaamil tha, aur yeh kab hua?",
}

HINGLISH_REVIEW: Dict[str, str] = {"status": APPROVED, "reviewer": "advay-sinha", "review_date": "2026-10-02"}


def _approved(record: Dict[str, str]) -> bool:
    return record.get("status") == APPROVED and bool(record.get("reviewer")) and bool(record.get("review_date"))


def english_variant(intent: str, rng: Optional[random.Random] = None) -> Optional[str]:
    """A reviewed English wording for `intent`, or None while variants are unapproved."""
    if not _approved(VARIANT_REVIEW):
        return None
    options = list(EN_VARIANTS.get(intent, []))
    approved_text = _intents.licensed_question(intent, "en") or _intents.fallback_text(intent, "en")
    if approved_text:
        options.append(approved_text)
    return (rng or random).choice(options) if options else None


def hinglish_text(intent: str) -> Optional[str]:
    """The reviewed Hinglish sentence for `intent`, or None while unapproved."""
    return HINGLISH_TEXT.get(intent) if _approved(HINGLISH_REVIEW) else None
