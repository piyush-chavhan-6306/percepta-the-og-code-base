"""
Border Intelligence Database Module.
Manages asynchronous SQLAlchemy 2.0 engine, WAL mode, session factory, and schema initialization.
"""
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.config import get_settings


class Base(DeclarativeBase):
    pass


# Global engine and sessionmaker
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str | None = None) -> AsyncEngine:
    """Initialize database engine with WAL mode and create all tables."""
    global _engine, _async_session_factory
    settings = get_settings()
    db_url = database_url or settings.DATABASE_URL

    _engine = create_async_engine(
        db_url,
        echo=False,
        future=True,
    )

    # Configure SQLite PRAGMA for high reliability & concurrency
    async with _engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.execute(text("PRAGMA busy_timeout=5000;"))
        await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_events_cam_time_seq ON event_logs (camera_id, timestamp, seq_id);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_events_cam_type_time_seq ON event_logs (camera_id, event_type, timestamp, seq_id);"))

    _async_session_factory = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the current async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        raise RuntimeError("Database must be initialized via init_db() before obtaining sessions")
    return _async_session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    global _async_session_factory
    if _async_session_factory is None:
        await init_db()
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Gracefully dispose database engine connections."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
