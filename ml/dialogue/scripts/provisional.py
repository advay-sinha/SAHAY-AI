"""Provisional local-demo fixed scripts (Controlled MVP Task 5D-L).

Pure module: standard library only, no I/O, no network, no model loading.

STATUS: PROVISIONAL, UNREVIEWED, LOCAL-DEMO ONLY.
------------------------------------------------------------------
The eight texts below are copied byte for byte from the Task 5C candidate
review packet, ``docs/dialogue/FIXED_SCRIPTS_CANDIDATE_REVIEW.md``, after each
content hash was verified. Every candidate there is still ``PENDING``: nobody
has reviewed or approved any of them, and nothing here records a reviewer, a
decision or a date.

These records are deliberately NOT part of ``fixed_scripts.SCRIPTS``. That
registry stays ``NOT_WRITTEN``, so ``text_for()`` still returns None, the policy
still reports ``script_available: False``, and ``GET /health`` still reports
``fixed_scripts_ready: false``. The backend may show these texts only through
its default-off, development/test-only feature flag, and only as text
(``audio: "none"``, PC-12). There is no audio asset for any of them.

No model selects, translates, rewrites or changes this text. The state machine
picks the state, the session language picks the language, and the S9 reference
number is substituted only through ``render_closing``.
"""

import hashlib
import re
from typing import Dict, Optional

from ..states import State

#: Label carried by every provisional record, audit entry and test.
STATUS = "PROVISIONAL_UNREVIEWED"
LOCAL_DEMO_ONLY = True
#: The persisted review_status of an assistant turn that used one of these texts.
TURN_REVIEW_STATUS = "provisional_unreviewed"
#: PC-12. Provisional scripts are text only and never claim audio.
AUDIO = "none"
AUDIO_READY = False

SOURCE_PACKET = "docs/dialogue/FIXED_SCRIPTS_CANDIDATE_REVIEW.md"

#: The only dynamic field, S9 only, exactly once per S9 text.
REFERENCE_TOKEN = "{reference_no}"
#: Current runtime reference format (backend/app/services/intake.py reference_for).
REFERENCE_PATTERN = re.compile(r"\ASAH-[0-9A-F]{6}\Z")

STATES = (State.S0_OPENING, State.SH_HUMAN_HANDOFF, State.SX_CRISIS, State.S9_CLOSING)
LANGS = ("en", "hi")


class ProvisionalScript:
    """One provisional text in one language, with the packet hash it must match."""

    __slots__ = ("state", "lang", "text", "sha256")

    def __init__(self, state: State, lang: str, text: str, sha256: str) -> None:
        self.state = state
        self.lang = lang
        self.text = text
        self.sha256 = sha256

    @property
    def key(self) -> str:
        return f"{self.state.value}:{self.lang}"

    def verified(self) -> bool:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest() == self.sha256


# BEGIN GENERATED FROM SOURCE_PACKET — do not edit by hand; any change invalidates review.
_RECORDS = (
    (State.S0_OPENING, 'en',
     'I am the SAHAY automated AI assistant. What you share may be reviewed by a human officer. You can ask for human help at any time. Please describe what happened in your own words.',
     '8296a38a8dde4a9cc1480b82cdc57ec97f3b3421acba49875aebbab38d8e7de2'),
    (State.S0_OPENING, 'hi',
     'मैं सहाय स्वचालित कृत्रिम बुद्धिमत्ता सहायक हूँ। आप जो साझा करते हैं, उसकी समीक्षा एक मानव अधिकारी द्वारा की जा सकती है। आप किसी भी समय किसी व्यक्ति से सहायता माँग सकते हैं। कृपया अपने शब्दों में बताइए कि क्या हुआ।',
     '8bf8bed902cd53a2dae73c31cb1e31422049db92f6e3e08f4ae585e9b2efedc5'),
    (State.SH_HUMAN_HANDOFF, 'en',
     'The AI assistant will not continue this conversation. Your session has been routed for human support. No officer has joined this session yet. Please stay in this session if you are able.',
     'd883bbddf6975370f68a6529b745a459c1f3fd033160c3a09ac22fa789c981c9'),
    (State.SH_HUMAN_HANDOFF, 'hi',
     'कृत्रिम बुद्धिमत्ता सहायक अब यह बातचीत जारी नहीं रखेगा। आपके सत्र को मानव सहायता के लिए भेज दिया गया है। अभी कोई अधिकारी इस सत्र में शामिल नहीं हुआ है। यदि आप सक्षम हों, तो कृपया इस सत्र में बने रहें।',
     'da39efc28d4f22c2c967c1f383bb2b8bb7dabdc158f574f91ea95010cda35de8'),
    (State.SX_CRISIS, 'en',
     'Thank you for telling me. Urgent human support has been requested. If you can, stay away from immediate danger and remain near a person you trust. Please stay in this session.',
     '2e8aad0e51696f6789b7ba57db3b34483c7a812029e55a460f1d6933ed3ad8c5'),
    (State.SX_CRISIS, 'hi',
     'यह बताने के लिए धन्यवाद। तत्काल मानव सहायता का अनुरोध किया गया है। यदि संभव हो, तो तत्काल खतरे से दूर रहें और किसी भरोसेमंद व्यक्ति के पास रहें। कृपया इस सत्र में बने रहें।',
     '68a40e233eb01a1a12592c559487c9520f8f70fb402e6233c5917ec09f473b9b'),
    (State.S9_CLOSING, 'en',
     'What you shared has been recorded. Your session reference number is {reference_no}. Authorized human officers can review your request. You can ask for human help if you need it.',
     'dc3094445f87503a1cd1541d9cf427630ea45a25463ccb94838bf50a6fee1349'),
    (State.S9_CLOSING, 'hi',
     'आपने जो साझा किया है, उसे दर्ज कर लिया गया है। आपके सत्र की संदर्भ संख्या {reference_no} है। अधिकृत मानव अधिकारी आपके अनुरोध की समीक्षा कर सकते हैं। आवश्यकता होने पर आप किसी व्यक्ति से सहायता माँग सकते हैं।',
     'fccc6bfeb3f0ffc11bf1c314ce4ac13608a382d5702c7f8866a8e75141b4509a'),
)
# END GENERATED FROM SOURCE_PACKET

PROVISIONAL_SCRIPTS: Dict[str, ProvisionalScript] = {
    f"{state.value}:{lang}": ProvisionalScript(state, lang, text, digest)
    for state, lang, text, digest in _RECORDS
}


def script_for(state: State, lang: str) -> Optional[ProvisionalScript]:
    """The provisional record for (state, lang), only if its hash still matches."""
    record = PROVISIONAL_SCRIPTS.get(f"{state.value}:{lang}")
    if record is None or not record.verified():
        return None
    return record


def all_verified() -> bool:
    """True only when all eight records exist and every hash matches."""
    keys = {f"{state.value}:{lang}" for state in STATES for lang in LANGS}
    return set(PROVISIONAL_SCRIPTS) == keys and all(r.verified() for r in PROVISIONAL_SCRIPTS.values())


def render_closing(template: str, reference: str) -> Optional[str]:
    """Substitute a validated reference into an S9 template, or return None.

    The template must contain the literal token exactly once and no other
    brace. The reference must match the runtime format exactly. Ownership and
    equality with persisted data are the caller's check; this function only
    refuses anything that is not a well-formed single-slot substitution.
    """
    if not isinstance(template, str) or not isinstance(reference, str):
        return None
    if template.count(REFERENCE_TOKEN) != 1:
        return None
    if "{" in template.replace(REFERENCE_TOKEN, "") or "}" in template.replace(REFERENCE_TOKEN, ""):
        return None
    if not REFERENCE_PATTERN.match(reference):
        return None
    return template.replace(REFERENCE_TOKEN, reference, 1)
