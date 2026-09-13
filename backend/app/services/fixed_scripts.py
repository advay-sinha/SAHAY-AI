"""One place that decides whether a fixed-script turn may be shown (Task 5D-L).

No fixed script is approved. `ml.dialogue.scripts.fixed_scripts` stays
NOT_WRITTEN, the policy still fails closed, and `GET /health` still reports
`fixed_scripts_ready: false`.

For a local demo only, `PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO` (default off,
refused at startup unless APP_ENV is development or test) lets the eight
PROVISIONAL, UNREVIEWED candidate texts appear as text-only assistant turns:

- `audio` is always "none" (PC-12). No asset exists, so "prerecorded" and
  "streaming" are never claimed.
- The deterministic state machine chooses the state and the session language
  chooses the text. No model selects, translates, rewrites or changes it.
- A text is shown only while its packet hash still matches.
- Every shown turn is persisted with review_status "provisional_unreviewed" and
  audited with the script hash, never with victim text.
- S9 carries the session's own persisted reference, substituted into the single
  `{reference_no}` slot only after ownership, format and equality checks.

Crisis handling is unchanged: SX routing, Critical, the alert and the takeover
request happen whether or not a provisional text is shown.
"""

from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ml.dialogue.intents import STATE_INTENT
from ml.dialogue.scripts import provisional
from ml.dialogue.states import State

from ..core.config import PROVISIONAL_SCRIPT_ENVS, get_settings
from ..models import Case, Session, Turn
from . import audit

SHOWN = "fixed_script.provisional_shown"
SUPPRESSED = "fixed_script.provisional_suppressed"


def provisional_enabled() -> bool:
    """The flag is on AND the environment permits it. Checked on every use."""
    settings = get_settings()
    return (
        getattr(settings, "PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO", False) is True
        and getattr(settings, "APP_ENV", None) in PROVISIONAL_SCRIPT_ENVS
    )


async def _suppress(db: AsyncSession, case: Case, state: State, reason: str) -> None:
    await audit.record(db, SUPPRESSED, case_id=case.id, detail={
        "state": state.value, "reason": reason, "status": provisional.STATUS})


async def _persisted_reference(db: AsyncSession, session: Session, case: Case) -> Optional[str]:
    """The session's own reference, only if every ownership and format check passes."""
    from .intake import reference_for  # intake imports this module

    stored = (await db.execute(
        select(Case.reference).where(Case.session_id == session.id)
    )).scalars().all()
    if case.session_id != session.id or len(stored) != 1:
        return None
    reference = stored[0]
    if (not isinstance(reference, str) or reference != case.reference
            or reference != reference_for(session.id)
            or not provisional.REFERENCE_PATTERN.match(reference)):
        return None
    return reference


async def show(
    db: AsyncSession, out: Any, session: Session, case: Case, state: State,
) -> Optional[Turn]:
    """Persist and queue one provisional fixed-script turn, or show nothing.

    Callers decide *whether* the state's trigger conditions hold. This function
    re-checks the flag, the language, the hash and, for S9, the reference.
    """
    if not provisional_enabled():
        return None
    lang = session.lang
    script = provisional.script_for(state, lang) if lang in provisional.LANGS else None
    if script is None:
        await _suppress(db, case, state, "unsupported_language" if lang not in provisional.LANGS
                        else "hash_mismatch")
        return None

    text = script.text
    if state is State.S9_CLOSING:
        reference = await _persisted_reference(db, session, case)
        text = provisional.render_closing(script.text, reference) if reference else None
        if text is None:
            await _suppress(db, case, state, "reference_invalid")
            return None
    elif provisional.REFERENCE_TOKEN in text:
        await _suppress(db, case, state, "unexpected_template")
        return None

    intent = STATE_INTENT[state]
    last_seq = (await db.execute(
        select(Turn.seq).where(Turn.session_id == session.id).order_by(Turn.seq.desc())
    )).scalars().first()
    turn = Turn(id=str(uuid4()), session_id=session.id, seq=(last_seq or 0) + 1, speaker="assistant",
                text=text, lang=lang, state=state.value, intent=intent, was_fallback=False,
                review_status=provisional.TURN_REVIEW_STATUS, created_at=audit.now())
    try:
        async with db.begin_nested():
            db.add(turn)
            await db.flush()
    except IntegrityError:
        await _suppress(db, case, state, "sequence_conflict")
        return None

    await audit.record(db, SHOWN, case_id=case.id, detail={
        "state": state.value, "lang": lang, "turn_id": turn.id, "script_sha256": script.sha256,
        "status": provisional.STATUS, "local_demo_only": True, "audio": provisional.AUDIO})
    out.add("assistant.turn", {"turn_id": turn.id, "text": turn.text, "lang": turn.lang,
                               "intent": intent, "audio": provisional.AUDIO})
    out.add("transcript.line", {"turn_id": turn.id, "speaker": "assistant", "text": turn.text,
                                "lang": turn.lang, "ts": turn.created_at.isoformat()})
    return turn
