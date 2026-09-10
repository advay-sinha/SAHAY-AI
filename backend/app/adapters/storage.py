"""Audio and file storage behind an interface. Local filesystem for the MVP.

Audio is retained only with consent, and only for AUDIO_RETENTION_HOURS.
Nothing here is committed to Git.
"""

from typing import Optional, Protocol


class AudioStorage(Protocol):
    name: str

    def put(self, session_id: str, turn_id: str, pcm16: bytes) -> Optional[str]:
        ...


class NullStorage:
    """Discards audio. Used when consent was not granted."""

    name = "null"

    def put(self, session_id: str, turn_id: str, pcm16: bytes) -> Optional[str]:
        return None
