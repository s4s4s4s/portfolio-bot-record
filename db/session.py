"""Async-engine + session-factory.

Ленивый init для удобства тестов: они могут override DATABASE_URL
через monkeypatch и затем вызвать reset_engine().
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings
from db.models import Base

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_data_dir(database_url: str) -> None:
    """Если SQLite — создаём папку под файл (см. H-1 в Healer hints)."""
    if not database_url.startswith("sqlite+aiosqlite:///"):
        return
    raw_path = database_url.split("sqlite+aiosqlite:///", 1)[1]
    if raw_path.startswith(":memory:"):
        return
    Path(raw_path).resolve().parent.mkdir(parents=True, exist_ok=True)


def _prepare_async_postgres_url(url: str) -> tuple[str, dict[str, object]]:
    """Превращает обычный Postgres URL (Neon/Supabase-style) в async-совместимый.

    Что делает:
      • postgresql:// → postgresql+asyncpg://
      • выкидывает sslmode/channel_binding из query (asyncpg их не понимает)
      • если был sslmode=require — возвращает connect_args={"ssl": True}
    """
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if not url.startswith("postgresql+asyncpg://"):
        return url, {}

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    ssl_required = "require" in query.get("sslmode", [])
    query.pop("sslmode", None)
    query.pop("channel_binding", None)
    cleaned = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    connect_args: dict[str, object] = {"ssl": True} if ssl_required else {}
    return cleaned, connect_args


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _ensure_data_dir(settings.database_url)
        url, connect_args = _prepare_async_postgres_url(settings.database_url)
        _engine = create_async_engine(
            url,
            future=True,
            echo=False,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Контекстный менеджер для одной сессии. Авто-rollback на исключении."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Создаёт схему из моделей. В production вместо этого — `alembic upgrade head`."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """Полное удаление всех таблиц. Используется только в тестах."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def reset_engine() -> None:
    """Сбросить ленивый кэш — нужно тестам после смены DATABASE_URL."""
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _factory = None
