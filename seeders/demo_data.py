"""Сидер demo-данных. Идемпотентен: повторный запуск не задвоит сущности.

Стратегия (демо салона красоты):
  • 3 услуги: стрижка / маникюр / массаж.
  • 2 мастера: Анна (стрижка+маникюр), Дмитрий (маникюр+массаж).
  • Слоты на 14 дней вперёд через services.slot_generator.

Запуск:
    python -m seeders.demo_data
"""
from __future__ import annotations

import asyncio

from db.repositories import MasterRepo, ServiceRepo
from db.session import get_session, init_db
from services.slot_generator import generate_slots_window


async def seed() -> dict[str, int]:
    await init_db()
    async with get_session() as session:
        svc_repo = ServiceRepo(session)
        haircut = await svc_repo.get_or_create(
            name="Стрижка (без окрашивания)", duration_min=60, price_kop=150_000,
        )
        manicure = await svc_repo.get_or_create(
            name="Маникюр", duration_min=90, price_kop=200_000,
        )
        massage = await svc_repo.get_or_create(
            name="Массаж", duration_min=60, price_kop=250_000,
        )
        await session.flush()

        master_repo = MasterRepo(session)
        anna = await master_repo.get_or_create(
            name="Анна",
            services_csv=f"{haircut.id},{manicure.id}",
            schedule={
                "mon": ["10:00", "20:00"],
                "tue": ["10:00", "20:00"],
                "wed": ["10:00", "20:00"],
                "thu": ["10:00", "20:00"],
                "fri": ["10:00", "20:00"],
            },
        )
        dmitry = await master_repo.get_or_create(
            name="Дмитрий",
            services_csv=f"{manicure.id},{massage.id}",
            schedule={
                "tue": ["11:00", "21:00"],
                "wed": ["11:00", "21:00"],
                "thu": ["11:00", "21:00"],
                "fri": ["11:00", "21:00"],
                "sat": ["11:00", "21:00"],
            },
        )
        await session.flush()

        slots_created = await generate_slots_window(session, days=14)
        await session.commit()

        return {
            "services": 3,
            "masters": 2,
            "anna_id": anna.id,
            "dmitry_id": dmitry.id,
            "slots_created": slots_created,
        }


_HAIRCUT_OLD = "Стрижка"
_HAIRCUT_NEW = "Стрижка (без окрашивания)"


async def migrate_legacy_service_names() -> bool:
    """Переименовывает услуги после обновления демо (идемпотентно)."""
    from sqlalchemy import select, update

    from db.models import Service

    async with get_session() as session:
        old = (
            await session.execute(select(Service).where(Service.name == _HAIRCUT_OLD))
        ).scalar_one_or_none()
        new = (
            await session.execute(select(Service).where(Service.name == _HAIRCUT_NEW))
        ).scalar_one_or_none()
        if old is None:
            return False
        if new is not None and new.id != old.id:
            old.is_active = False
            await session.commit()
            return True
        result = await session.execute(
            update(Service).where(Service.id == old.id).values(name=_HAIRCUT_NEW),
        )
        await session.commit()
        return result.rowcount > 0


async def ensure_demo_data_if_empty() -> dict[str, int] | None:
    """Сидит демо, если в БД нет активных услуг или мастеров."""
    async with get_session() as session:
        services = await ServiceRepo(session).list_active()
        masters = await MasterRepo(session).list_active()
        if services and masters:
            return None
    return await seed()


def main() -> None:
    result = asyncio.run(seed())
    print(
        f"✅ Seed готов: services={result['services']}, masters={result['masters']}, "
        f"slots_created={result['slots_created']}",
    )


if __name__ == "__main__":
    main()
