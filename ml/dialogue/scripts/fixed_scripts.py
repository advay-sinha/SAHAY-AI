"""Fixed, pre-approved scripts for S0, S9, SX and SH.

Pure module: standard library only, no I/O. Text is a constant here; the
pre-synthesised WAV files live under DATA_ROOT and are referenced by name only.

STATUS: NOT WRITTEN.
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


#: (state, lang) -> ScriptRecord. Populating a record is a `type:dialogue`
#: change: two reviewers, STATES.md updated in the same commit.
SCRIPTS: Dict[str, ScriptRecord] = {
    f"{state.value}:{lang}": _blank(state, lang)
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
        "Confirms the account is recorded. Gives the reference number. States what "
        "happens next. No promise of any outcome, timeline, arrest or compensation."
    ),
    State.SX_CRISIS: (
        "Acknowledges. States plainly that a person will speak with them now. Asks "
        "them to stay. Nothing else: no advice, no assessment, no question. "
        "Requires counsellor or psychology faculty review before Day 8."
    ),
    State.SH_HUMAN_HANDOFF: (
        "Confirms the transfer to a person and asks them to stay on the line. "
        "No advice, no assessment."
    ),
}


def record_for(state: State, lang: str) -> Optional[ScriptRecord]:
    return SCRIPTS.get(f"{state.value}:{lang}")


def text_for(state: State, lang: str) -> Optional[str]:
    """Return approved fixed-script text, or None if it may not be spoken."""
    record = record_for(state, lang)
    if record is None or not record.speakable:
        return None
    return record.text


def unwritten() -> Dict[str, str]:
    """Return {key: status} for every script that is not yet speakable."""
    return {key: rec.status for key, rec in SCRIPTS.items() if not rec.speakable}
