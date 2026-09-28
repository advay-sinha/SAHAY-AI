"""Per-turn latency measurements (HANDOVER M2; CONTRACTS.md section 8).

Rows go into the existing ``latency_metrics`` table. They are internal operational data: never
sent to the victim or the console, and they carry no text. Only the stage names below are
stored, so a caller cannot write arbitrary keys.
"""

from typing import Any, Mapping, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tables import LatencyMetric

#: Stages measured on the server. VAD endpointing and the first TTS chunk happen elsewhere
#: (the phone, and M13), so they are not recorded here.
STAGES = (
    "asr_request",          # backend -> loopback speech-to-text process and back
    "asr_service_decode",   # inside that process: audio decode
    "asr_service_asr",      # inside that process: VAD + Whisper
    "asr_service_total",
    "safety_precheck",
    "dialogue_policy",
    "llm_phrasing",
    "output_validator",
    "reply_path",           # submit_turn: victim turn received -> reply text ready
    "request_total",        # audio endpoint: request body received -> response ready
)
ASR_SERVICE_KEYS = {"decode": "asr_service_decode", "asr": "asr_service_asr", "total": "asr_service_total"}


def record(db: AsyncSession, session_id: str, turn_id: Optional[str], timings: Mapping[str, Any]) -> int:
    """Add one row per known stage with a numeric duration. Returns the number of rows added."""
    added = 0
    for stage, value in timings.items():
        if stage not in STAGES or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        db.add(LatencyMetric(id=str(uuid4()), session_id=session_id, turn_id=turn_id, stage=stage,
                             duration_ms=float(value)))
        added += 1
    return added


def asr_service_timings(asr: Optional[Mapping[str, Any]]) -> dict:
    """The speech-to-text process's own ``timings_ms``, renamed to stage names."""
    raw = (asr or {}).get("timings_ms") or {}
    return {ASR_SERVICE_KEYS[k]: v for k, v in raw.items() if k in ASR_SERVICE_KEYS}
