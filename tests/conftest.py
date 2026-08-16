"""Async-фикстуры для тестов: in-memory SQLite + чистая БД на каждый тест."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from aiogram.types import Message, User


def create_message(text: str, *, user_id: int = 42, username: str = "test") -> Message:
    """Фейковое Message для тестов хендлеров."""
    return Message(
        message_id=1,
        date=__import__("datetime").datetime.utcnow(),
        from_user=User(id=user_id, is_bot=False, first_name="T"),
        chat=__import__("aiogram.types").types.Chat(id=user_id, type="private"),
        text=text,
    )


@pytest.fixture(scope="session", autouse=True)
def _ensure_env() -> None:
    """Стабильные значения ENV для тестов.

    Пишем напрямую (не setdefault): CI задаёт свои BOT_TOKEN/ADMIN_IDS на
    уровне job (см. .github/workflows/ci.yml), и setdefault ничего не
    менял бы поверх них — тесты, ожидающие конкретные значения (см.
    test_settings_load_with_env), тогда ловили бы чужие.
    """
    os.environ["BOT_TOKEN"] = "test:token"
    os.environ["ADMIN_IDS"] = "111,222"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["LOG_LEVEL"] = "WARNING"


@pytest.fixture(autouse=True)
def _mock_human_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_say(
        scene: str,
        facts: dict | None = None,
        *,
        user_text: str = "",
        llm=None,
        temperature: float = 0.78,
    ) -> str:
        parts = [scene]
        if facts:
            parts.append(str(facts))
        if user_text:
            parts.append(user_text[:60])
        return " · ".join(parts)

    monkeypatch.setattr("services.human_reply.say", _fake_say)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[object]:
    """Чистая БД на каждый тест.

    Используется in-memory SQLite через `StaticPool`, чтобы все
    подключения видели одну и ту же БД (по умолчанию sqlite+aiosqlite
    выдаёт *разные* in-memory БД на каждое подключение).
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from db.models import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def session_with_seed(session: object) -> object:  # type: ignore[type-arg]
    """Сессия с уже добавленными mock-услугами и мастерами на 14 дней."""
    from db.repositories import MasterRepo, ServiceRepo
    from services.slot_generator import generate_slots_window

    s = session  # type: ignore[assignment]
    svc_repo = ServiceRepo(s)  # type: ignore[arg-type]
    haircut = await svc_repo.get_or_create(
        name="Стрижка (без окрашивания)", duration_min=60, price_kop=150_000,
    )
    coloring = await svc_repo.get_or_create(name="Окрашивание", duration_min=180, price_kop=450_000)
    manicure = await svc_repo.get_or_create(name="Маникюр", duration_min=90, price_kop=200_000)
    await s.flush()  # type: ignore[attr-defined]

    master_repo = MasterRepo(s)  # type: ignore[arg-type]
    await master_repo.get_or_create(
        name="Анна",
        services_csv=f"{haircut.id},{coloring.id}",
        schedule={
            "mon": ["10:00", "20:00"], "tue": ["10:00", "20:00"],
            "wed": ["10:00", "20:00"], "thu": ["10:00", "20:00"],
            "fri": ["10:00", "20:00"],
        },
    )
    await master_repo.get_or_create(
        name="Мария",
        services_csv=f"{haircut.id},{manicure.id}",
        schedule={
            "tue": ["11:00", "21:00"], "wed": ["11:00", "21:00"],
            "thu": ["11:00", "21:00"], "fri": ["11:00", "21:00"],
            "sat": ["11:00", "21:00"],
        },
    )
    await s.flush()  # type: ignore[attr-defined]
    await generate_slots_window(s, days=14)  # type: ignore[arg-type]
    return s
