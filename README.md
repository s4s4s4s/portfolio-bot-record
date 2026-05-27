# aiogram-booking

![banner](docs/banner.svg)

> Универсальный Telegram-бот **записи клиентов**. Шаблон Wave 4 экосистемы Jarvis.
> Из коробки покрывает beauty-салон, медклинику, барбершоп, автосервис, репетитора.

## Что внутри

- **aiogram 3.x** — асинхронный фреймворк для Telegram-ботов
- **SQLAlchemy 2.x async** + `aiosqlite` — БД (одной строкой переключаемо на PostgreSQL)
- **APScheduler** с `SQLAlchemyJobStore` — напоминания переживают рестарт
- **pydantic-settings** — типизированный конфиг через `.env`
- **loguru** — структурные логи (JSON в проде, человекочитаемые в dev)
- **alembic** — миграции
- **pytest + freezegun** — 54 теста, асинхронные, in-memory SQLite

## Скоуп

- `/start`, `/help`, `/cancel` + inline-меню (основной UX без слэшей в подсказках)
- Запись текстом/голосом (NLU): «запиши на френч завтра», «когда свободен Дмитрий»
- `/book` — FSM: услуга → мастер → дата → слот → имя → телефон → подтверждение
- `/my` — список своих записей + отмена
- `AUTO_SEED_DEMO=true` — демо-данные при первом старте (Анна, Дмитрий, 14 дней слотов)
- Лимит **100 сообщений/день** на пользователя; 3 нарушения → блок (`/unblock` у админа)
- `/admin`, `/today`, `/tomorrow`, `/add_slot`, `/block_slot`, `/broadcast` (только для `ADMIN_IDS`)
- Напоминания за 24h и 2h до записи (cron-job с дедупликацией)
- Скользящее окно слотов: каждый день в 03:00 догенерирует +1 день вперёд

## Запуск локально

```bash
cp .env.example .env
# отредактировать .env: BOT_TOKEN, ADMIN_IDS

python -m pip install -r requirements.txt
python -m seeders.demo_data         # опционально; иначе AUTO_SEED_DEMO при пустой БД
python -m bot.main                  # старт бота (нужны GROQ_API_KEY для NLU/голоса)
```

Или через Docker:

```bash
docker compose up --build
```

## Тесты

```bash
pytest tests/ -v --asyncio-mode=auto
ruff check .
mypy --strict bot db services core seeders
```

## Деплой на Railway

Подробный пошаговый гайд: [`docs/DEPLOY_RAILWAY.md`](docs/DEPLOY_RAILWAY.md).
TL;DR:

1. Создать проект в Railway, подключить этот репо.
2. Добавить ENV: `BOT_TOKEN`, `ADMIN_IDS`, `TZ=Europe/Moscow`, `LOG_JSON=true`.
3. Volume `/app/data` для SQLite (или подключить Railway PostgreSQL и выставить `DATABASE_URL=postgresql+asyncpg://...`).
4. Railway автоматически использует `Dockerfile`. После первого деплоя один раз: `railway run python -m seeders.demo_data`.

## CI / Pre-commit

- `.github/workflows/ci.yml` — ruff + mypy + pytest + Docker-build на каждый push/PR.
- `.pre-commit-config.yaml` — локальные хуки. Установка:
  ```bash
  pip install pre-commit && pre-commit install
  ```

## Кейс-стади

`docs/case-study.mdx` — публикуется на портфолио-сайте. Содержит
архитектуру (Mermaid), решения, метрики качества.

## Архитектура

См. `docs/architecture.mmd` (Mermaid). Если просматриваете на GitHub — он рендерится автоматически.

```
bot/        — aiogram-роутеры, FSM, клавиатуры, фильтры, middlewares
db/         — модели, async-engine, репозитории
services/   — phone, slot_generator, scheduler, notifier
seeders/    — demo_data (idempotent)
core/       — config (pydantic-settings), logging (loguru)
tests/      — pytest, in-memory SQLite
```

## Расширение

- **Платежи**: точка расширения через `Service.requires_prepayment` (поле зарезервировано).
- **CRM-интеграции**: `services/integrations/` (Bizon365, AmoCRM, GetCourse) — ABC `CRMSync`.
- **Мульти-локация**: добавить `Master.location_id` (опциональное FK).

## Лицензия

MIT — см. `LICENSE`.
