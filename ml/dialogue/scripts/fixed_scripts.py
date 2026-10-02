"""Fixed, pre-approved scripts for S0, S9, SX and SH.

Pure module: standard library only, no I/O. Text is a constant here; the
pre-synthesised WAV files live under DATA_ROOT and are referenced by name only.

STATUS: DRAFTED, IN REVIEW (2026-10-01). Not speakable until approved.
------------------------------------------------------------------
docs/dialogue/STATES.md records these as outstanding, owned by Team A / A2 and
due before Day 3. They are never model-generated. SX additionally requires a
counsellor or psychology faculty review before Day 8, and that reviewer must be
named in the deck.

This module therefore ships the required *structure* and an explicit refusal,
not invented victim-facing crisis text. `text_for()` returns None until a
reviewed script is recorded here, and `backend` must fail closed rather than
speak anything when it does.
"""

from typing import Dict, Optional

from ..states import State

NOT_WRITTEN = "NOT_WRITTEN"
IN_REVIEW = "IN_REVIEW"
APPROVED = "APPROVED"


class ScriptRecord:
    """One fixed script in one language, with its provenance."""

    __slots__ = ("state", "lang", "text", "status", "reviewer", "review_date", "audio_asset")

    def __init__(
        self,
        state: State,
        lang: str,
        text: Optional[str] = None,
        status: str = NOT_WRITTEN,
        reviewer: Optional[str] = None,
        review_date: Optional[str] = None,
        audio_asset: Optional[str] = None,
    ) -> None:
        self.state = state
        self.lang = lang
        self.text = text
        self.status = status
        self.reviewer = reviewer
        self.review_date = review_date
        self.audio_asset = audio_asset

    @property
    def speakable(self) -> bool:
        return self.status == APPROVED and bool(self.text)


def _blank(state: State, lang: str) -> ScriptRecord:
    return ScriptRecord(state=state, lang=lang)


#: Drafted 2026-10-01 from published guidance (sources and rationale:
#: docs/dialogue/FIXED_SCRIPTS_SOURCES.md). IN_REVIEW is not speakable: text_for()
#: still returns None until a record is APPROVED with a named reviewer and date.
DRAFT_TEXT: Dict[str, str] = {
    "S0:en": (
        "I am SAHAY, an AI assistant, not a person. "
        "A human support officer can read everything you share here, and you can ask "
        "to talk to a person at any time. "
        "When you are ready, tell me what happened, in your own words; you can share as "
        "much or as little as you want."
    ),
    "S0:hi": (
        "मैं सहाय हूँ, एक एआई सहायक, कोई इंसान नहीं। "
        "आप यहाँ जो भी बताएँ, उसे सहायता अधिकारी पढ़ सकते हैं, और जब भी चाहें, "
        "किसी व्यक्ति से बात करने के लिए कहिए। "
        "जब आप तैयार हों, अपने शब्दों में बताइए कि क्या हुआ; आप जितना चाहें, उतना ही बताइए।"
    ),
    "S9:en": (
        "Thank you. What you shared has been saved. "
        "A human support officer can review it, and you can see its status under "
        "My requests, where your reference number is shown. "
        "You can ask to talk to a person at any time."
    ),
    "S9:hi": (
        "धन्यवाद, आपकी बात सहेज ली गई है। "
        "सहायता अधिकारी इसे देख सकते हैं, और \"मेरे अनुरोध\" में इसकी स्थिति देखी जा "
        "सकती है, जहाँ आपकी संदर्भ संख्या दी गई है। "
        "जब भी चाहें, किसी व्यक्ति से बात करने के लिए कहिए।"
    ),
    "SX:en": (
        "Thank you for telling me. "
        "I am connecting you to a person right now. "
        "Please stay in this conversation."
    ),
    "SX:hi": (
        "आपने मुझे यह बताया, इसके लिए धन्यवाद। "
        "आपको अभी एक व्यक्ति से जोड़ा जा रहा है। "
        "कृपया इस बातचीत में बने रहिए।"
    ),
    "SH:en": (
        "I am connecting you to a person now. "
        "Please stay in this conversation; they can see everything you share here."
    ),
    "SH:hi": (
        "आपको अभी एक व्यक्ति से जोड़ा जा रहा है। "
        "कृपया इस बातचीत में बने रहिए; आप यहाँ जो भी बताएँ, वह उन्हें दिखेगा।"
    ),
}


def _draft(state: State, lang: str) -> ScriptRecord:
    key = f"{state.value}:{lang}"
    text = DRAFT_TEXT.get(key)
    return ScriptRecord(state=state, lang=lang, text=text, status=IN_REVIEW if text else NOT_WRITTEN)


#: (state, lang) -> ScriptRecord. Populating a record is a `type:dialogue`
#: change: two reviewers, STATES.md updated in the same commit.
SCRIPTS: Dict[str, ScriptRecord] = {
    f"{state.value}:{lang}": _draft(state, lang)
    for state in (State.S0_OPENING, State.S9_CLOSING, State.SX_CRISIS, State.SH_HUMAN_HANDOFF)
    for lang in ("hi", "en")
}

#: What each script must contain, so the author and the reviewer agree in advance.
REQUIRED_CONTENT: Dict[State, str] = {
    State.S0_OPENING: (
        "Identifies the assistant as an AI. States that a human officer reviews "
        "everything. States the right to a human at any time. Invites the person "
        "to speak in their own words. No question."
    ),
    State.S9_CLOSING: (
        "Confirms the account is saved. Points to where the reference number is shown "
        "(it is not read aloud). States what happens next. No promise of any outcome, "
        "timeline, arrest, callback or compensation, and no wording that implies an "
        "official complaint or FIR has been registered."
    ),
    State.SX_CRISIS: (
        "Acknowledges. States plainly that a person will speak with them now. Asks "
        "them to stay. Nothing else: no advice, no assessment, no question. "
        "Requires counsellor or psychology faculty review before Day 8."
    ),
    State.SH_HUMAN_HANDOFF: (
        "Confirms the transfer to a person and asks them to stay in the conversation "
        "(not in a physical place). No advice, no assessment, no wait time."
    ),
}


def record_for(state: State, lang: str) -> Optional[ScriptRecord]:
    return SCRIPTS.get(f"{state.value}:{lang}")


def text_for(state: State, lang: str) -> Optional[str]:
    """Return approved fixed-script text, or None if it may not be spoken.

    The scripts go live as a set: none is spoken in a language until SX in
    that language is approved, so ordinary turns can never get a spoken reply
    while a crisis turn would get silence.
    """
    record = record_for(state, lang)
    if record is None or not record.speakable:
        return None
    crisis = record_for(State.SX_CRISIS, lang)
    if crisis is None or not crisis.speakable:
        return None
    return record.text


def unwritten() -> Dict[str, str]:
    """Return {key: status} for every script that is not yet speakable."""
    return {key: rec.status for key, rec in SCRIPTS.items() if not rec.speakable}
