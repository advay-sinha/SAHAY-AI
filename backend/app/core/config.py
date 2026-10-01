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

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

#: config.py -> core -> app -> backend -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]

_SQLITE_PREFIXES = ("sqlite+aiosqlite:///", "sqlite:///")
_DATABASE_CONFIGURATION_ERROR = "database configuration is invalid"


class DatabaseConfigurationError(ValueError):
    """Fixed-message database configuration failure that never carries a URL."""


_DEFAULT_SECRET_KEY = "change-me-in-.env"
_MIN_SECRET_KEY_LENGTH = 32


class SecretKeyConfigurationError(ValueError):
    """The JWT signing key is the committed default or too short to trust."""


def normalize_database_url(value: str, *, app_env: str) -> str:
    """Return an async SQLAlchemy URL without rebuilding credential fields.

    Normal application environments require encrypted PostgreSQL. SQLite is
    intentionally limited to explicit test/scenario processes.
    """
    try:
        url = make_url(value)
    except (ArgumentError, TypeError, ValueError):
        raise DatabaseConfigurationError(_DATABASE_CONFIGURATION_ERROR) from None

    backend = url.get_backend_name()
    if backend == "sqlite":
        if app_env != "test":
            raise DatabaseConfigurationError(_DATABASE_CONFIGURATION_ERROR)
        if url.drivername not in {"sqlite", "sqlite+aiosqlite"}:
            raise DatabaseConfigurationError(_DATABASE_CONFIGURATION_ERROR)
        database = url.database
        if not database:
            raise DatabaseConfigurationError(_DATABASE_CONFIGURATION_ERROR)
        if database != ":memory:":
            database = _anchor(database).replace("\\", "/")
        return url.set(drivername="sqlite+aiosqlite", database=database).render_as_string(
            hide_password=False
        )

    if backend != "postgresql" or not url.host or not url.database or url.port == 6543:
        raise DatabaseConfigurationError(_DATABASE_CONFIGURATION_ERROR)
    if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise DatabaseConfigurationError(_DATABASE_CONFIGURATION_ERROR)

    query = dict(url.query)
    ssl_value = query.pop("sslmode", None) or query.get("ssl")
    if ssl_value is not None and str(ssl_value).casefold() not in {
        "require",
        "verify-ca",
        "verify-full",
    }:
        raise DatabaseConfigurationError(_DATABASE_CONFIGURATION_ERROR)
    query["ssl"] = str(ssl_value or "require")
    normalized = url.set(drivername="postgresql+asyncpg", query=query)
    return normalized.render_as_string(hide_password=False)


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
    APP_ENV: Literal["development", "local", "demo", "test", "production"] = "development"
    HOST: str = "0.0.0.0"  # bound wide so a physical phone on the LAN can reach it
    PORT: int = 8000

    # Required: normal startup never silently falls back to a local database.
    DATABASE_URL: str
    MIGRATION_DATABASE_URL: str | None = None
    DATABASE_POOL_SIZE: int = Field(default=5, ge=1, le=10)
    DATABASE_MAX_OVERFLOW: int = Field(default=2, ge=0, le=10)
    DATABASE_POOL_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=60)
    DATABASE_CONNECT_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=60)
    DATABASE_COMMAND_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=300)
    SUPABASE_PROJECT_REF: str = ""
    REMOTE_DEMO_SEED_CONFIRMATION: str = ""

    FRONTEND_ORIGIN: str = "http://localhost:5173"
    MOBILE_API_URL: str = "http://localhost:8000"

    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 480

    # Adapters. The complete dialogue must run with LLM_PROVIDER=mock.
    LLM_PROVIDER: Literal["mock", "external"] = "mock"
    LLM_MODEL: str = ""
    LLM_API_KEY: str = ""
    # Speech recognition (EXT-120, PC-11). "mock" needs nothing running; "local_service" calls the
    # ML-owned speech-to-text process, which listens on the loopback interface only.
    ASR_PROVIDER: Literal["mock", "local_service"] = "mock"
    ASR_SERVICE_URL: str = "http://127.0.0.1:8765"
    ASR_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=120)
    # Voice output (EXT-103, PC-12). "none" returns no audio (the client shows the text);
    # "windows_voice" speaks validated turns with a built-in offline Windows voice. Fixed scripts
    # (S0, S9, SX, SH) are only ever played from approved human recordings in FIXED_AUDIO_ROOT.
    TTS_PROVIDER: Literal["none", "windows_voice"] = "none"
    FIXED_AUDIO_ROOT: str = "./runtime/audio/fixed"
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


    @field_validator("ASR_SERVICE_URL")
    @classmethod
    def _loopback_asr(cls, value: str) -> str:
        from urllib.parse import urlparse
        url = urlparse(value)
        if url.scheme != "http" or url.hostname not in ("127.0.0.1", "::1") or url.path not in ("", "/"):
            raise ValueError("ASR_SERVICE_URL must be http://127.0.0.1:<port> or http://[::1]:<port>")
        return value.rstrip("/")

    @field_validator("AUDIO_STORAGE_PATH", "FIXED_AUDIO_ROOT")
    @classmethod
    def _anchor_audio_path(cls, value: str) -> str:
        return _anchor(value) if value else value

    def ensure_runtime_dirs(self) -> None:
        """Create non-database runtime directories and guarded test DB parents."""
        Path(self.AUDIO_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        url = make_url(self.database_url())
        if url.get_backend_name() == "sqlite" and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)

    def require_signing_key(self) -> None:
        """Refuse to serve outside tests with a guessable JWT key.

        The role claim in the token is what the fan-out trusts, so a known key
        would let anyone mint an executive token. Never echoes the value.
        """
        if self.APP_ENV == "test":
            return
        if self.SECRET_KEY == _DEFAULT_SECRET_KEY or len(self.SECRET_KEY) < _MIN_SECRET_KEY_LENGTH:
            raise SecretKeyConfigurationError(
                f"SECRET_KEY must be set to a random value of at least {_MIN_SECRET_KEY_LENGTH} characters"
            )

    def database_url(self, *, for_migration: bool = False) -> str:
        raw = self.MIGRATION_DATABASE_URL if for_migration and self.MIGRATION_DATABASE_URL else self.DATABASE_URL
        return normalize_database_url(raw, app_env=self.APP_ENV)


@lru_cache
def get_settings() -> Settings:
    return Settings()
