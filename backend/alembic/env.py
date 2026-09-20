"""Alembic environment.

Reads the database URL from settings so local SQLite and a later PostgreSQL
target use the same migration history.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool

from app.core.config import get_settings
from app.core.db import Base
import app.models  # noqa: F401  ensures every table is registered on Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
migration_url = settings.database_url(for_migration=True)
# ConfigParser treats percent signs as interpolation markers. Escaping here
# preserves an already encoded credential without parsing or rebuilding it.
config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    is_sqlite = make_url(migration_url).get_backend_name() == "sqlite"
    context.configure(
        url=migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        migration_url,
        poolclass=pool.NullPool,
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.DATABASE_CONNECT_TIMEOUT_SECONDS,
            **(
                {"command_timeout": settings.DATABASE_COMMAND_TIMEOUT_SECONDS}
                if make_url(migration_url).get_backend_name() == "postgresql"
                else {}
            ),
        },
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    except Exception:
        raise RuntimeError("database migration failed") from None
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
