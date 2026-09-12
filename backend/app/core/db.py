"""Async SQLAlchemy persistence for PostgreSQL and local SQLite."""

from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_database_url = _settings.database_url()
_settings.ensure_runtime_dirs()


def engine_options(settings, database_url: str) -> dict:
    """Build dialect-appropriate options without exposing the configured URL."""
    url = make_url(database_url)
    options = {"echo": False, "pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"timeout": settings.DATABASE_CONNECT_TIMEOUT_SECONDS}
    else:
        options.update(
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
            connect_args={
                "timeout": settings.DATABASE_CONNECT_TIMEOUT_SECONDS,
                "command_timeout": settings.DATABASE_COMMAND_TIMEOUT_SECONDS,
            },
        )
    return options


engine = create_async_engine(_database_url, **engine_options(_settings, _database_url))
if engine.url.get_backend_name() == "sqlite":
    attach_target = engine
else:
    attach_target = None

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


#: The factory every request AND the background assessment runner use. Tests and
#: the scenario runner swap it for a disposable database with
#: `use_session_factory`, so API calls and background work never diverge.
_factory: async_sessionmaker = SessionLocal


def use_session_factory(factory: async_sessionmaker) -> None:
    global _factory
    _factory = factory


def session_factory() -> async_sessionmaker:
    return _factory


def attach_sqlite_pragmas(target_engine) -> None:
    """Apply the same PRAGMAs to another engine (disposable test/scenario DBs)."""

    if target_engine.url.get_backend_name() != "sqlite":
        return

    @event.listens_for(target_engine.sync_engine, "connect")
    def _pragmas(dbapi_connection, connection_record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


if attach_target is not None:
    attach_sqlite_pragmas(attach_target)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _factory() as session:
        yield session


async def dispose_engine() -> None:
    """Release the application engine's pool during process shutdown."""
    await engine.dispose()
