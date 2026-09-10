"""Consent gate.

Root CLAUDE.md invariants 6, 7 and 8, and CONTRACTS.md section 7:
  * Consent declined suppresses scoring entirely.
  * The session still reaches a human. Declining consent is not a dead end.
  * The AI disclosure and the "Talk to a person" control stay available
    throughout intake, regardless of consent.

Standard library only.
"""

from typing import Any, Dict, Optional

CONSENT_GRANTED = "granted"
CONSENT_DECLINED = "declined"
CONSENT_PENDING = "pending"


def session_capabilities(consent: Optional[str]) -> Dict[str, Any]:
    """What a session may do at this consent state."""
    granted = consent == CONSENT_GRANTED
    return {
        "consent": consent or CONSENT_PENDING,
        # Assessment only ever runs on an explicit grant.
        "assessment_enabled": granted,
        "scoring_enabled": granted,
        "audio_retained": granted,
        # These are unconditional. They do not depend on consent.
        "ai_disclosure_visible": True,
        "human_request_available": True,
        "routes_to_human": True,
    }


def may_assess(consent: Optional[str]) -> bool:
    return consent == CONSENT_GRANTED
