from __future__ import annotations

from backend.app.config import Settings


def create_sessionmaker(settings: Settings):
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install sqlalchemy[asyncio] and asyncpg to use database sessions") from exc

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)

