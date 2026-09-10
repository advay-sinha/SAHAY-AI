"""Runtime configuration. Values come from .env; no secret is committed.

Requires pydantic-settings (EXT-001, APPROVED 2026-09-10).

Relative paths in .env are resolved against the REPOSITORY ROOT, not the
current working directory. `scripts/start-backend.ps1` runs uvicorn from
`backend/`, and Alembic runs from `backend/` too, so a bare `./runtime/db`
would otherwise create a second `backend/runtime/` tree beside the real one.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: config.py -> core -> app -> backend -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]

_SQLITE_PREFIXES = ("sqlite+aiosqlite:///", "sqlite:///")


def _anchor(path: str) -> str:
    """Resolve a relative filesystem path against the repository root."""
    candidate = Path(path)
    if candidate.is_absolute():
        return str(candidate)
    return str((REPO_ROOT / candidate).resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Values follow .env.example, which is the project's committed env contract.
    APP_ENV: Literal["development", "local", "demo"] = "development"
    HOST: str = "0.0.0.0"  # bound wide so a physical phone on the LAN can reach it
    PORT: int = 8000

    # SQLite for the local MVP, behind SQLAlchemy so PostgreSQL can follow.
    DATABASE_URL: str = "sqlite+aiosqlite:///./runtime/db/sahay.db"

    FRONTEND_ORIGIN: str = "http://localhost:5173"
    MOBILE_API_URL: str = "http://localhost:8000"

    SECRET_KEY: str = "change-me-in-.env"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 480

    # Adapters. The complete dialogue must run with LLM_PROVIDER=mock.
    LLM_PROVIDER: Literal["mock", "external"] = "mock"
    LLM_MODEL: str = ""
    LLM_API_KEY: str = ""
    ASSESSMENT_RUNNER: Literal["local", "external"] = "local"
    # "local" is the deterministic keyword index; "external" is reserved for a
    # future vector store. Mirrors the local/external naming ASSESSMENT_RUNNER uses.
    POLICY_RETRIEVER: Literal["local", "external"] = "local"

    # Model paths stay empty until the matching external decision is APPROVED.
    ASR_MODEL_PATH: str = ""
    VAD_MODEL_PATH: str = ""
    TTS_MODEL_PATH: str = ""
    SER_MODEL_PATH: str = ""
    CLASSIFIER_MODEL_PATH: str = ""

    DATA_ROOT: str = ""
    AUDIO_STORAGE_PATH: str = "./runtime/audio"
    AUDIO_RETENTION_HOURS: int = 72
    AUDIO_FRAME_MS: int = 500

    SVI_CONFIDENCE_FLOOR: float = 0.45
    TURN_LATENCY_TARGET_MS: int = 3000
    VAD_SILENCE_MS: int = 700


    @field_validator("DATABASE_URL")
    @classmethod
    def _anchor_sqlite_path(cls, value: str) -> str:
        for prefix in _SQLITE_PREFIXES:
            if value.startswith(prefix):
                target = value[len(prefix) :]
                if target in ("", ":memory:"):
                    return value
                return prefix + _anchor(target).replace("\\", "/")
        # Not SQLite (a future PostgreSQL URL); leave it alone.
        return value

    @field_validator("AUDIO_STORAGE_PATH")
    @classmethod
    def _anchor_audio_path(cls, value: str) -> str:
        return _anchor(value) if value else value

    def ensure_runtime_dirs(self) -> None:
        """Create the local runtime directories if a fresh clone lacks them."""
        Path(self.AUDIO_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        for prefix in _SQLITE_PREFIXES:
            if self.DATABASE_URL.startswith(prefix):
                target = self.DATABASE_URL[len(prefix) :]
                if target and target != ":memory:":
                    Path(target).parent.mkdir(parents=True, exist_ok=True)
                break


@lru_cache
def get_settings() -> Settings:
    return Settings()
