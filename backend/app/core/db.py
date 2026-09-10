"""SQLite persistence through SQLAlchemy.

Local MVP only. Everything sits behind SQLAlchemy so a later PostgreSQL
migration is a configuration and migration exercise, not a rewrite.

Foreign keys, WAL and a busy timeout are enabled per docs/LOCAL_SETUP.md;
SQLite has foreign keys off by default, which would silently accept orphaned
audit rows.
"""

from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_settings.ensure_runtime_dirs()

engine = create_async_engine(
    _settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"timeout": 30},
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record):  # pragma: no cover - driver hook
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
