"""Alembic env.py — async SQLAlchemy 2 pattern.

The database URL is read from pydantic-settings (DATABASE_URL env var / .env file).
Run migrations from repo root:

    python -m alembic upgrade head
    python -m alembic revision --autogenerate -m "describe change"
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so api.app.* are importable
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Load app models and settings
# ---------------------------------------------------------------------------
from api.app.config import settings  # noqa: E402
from api.app.models import Base  # noqa: E402

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode — emit SQL to stdout without a live connection
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Tell Alembic to render JSONB and UUID types correctly
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connect and run migrations
# ---------------------------------------------------------------------------
async def run_async_migrations() -> None:
    """Create a temporary async engine, connect, and run migrations."""
    engine = create_async_engine(settings.database_url, poolclass=None)

    async with engine.connect() as conn:
        await conn.run_sync(_run_migrations_with_connection)

    await engine.dispose()


def _run_migrations_with_connection(connection) -> None:  # type: ignore[type-arg]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Entry point for online mode — wraps the async runner."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
