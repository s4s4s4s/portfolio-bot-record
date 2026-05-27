# SPEC — `aiogram-booking` (Wave 4)

> **Назначение**: универсальный бот записи клиентов. Продаётся beauty-салонам,
> медицинским клиникам, барбершопам, автосервисам, репетиторам. Один и тот же
> код адаптируется под любую сервисную нишу за 1–2 дня.

Этот документ — **контракт шаблона**. Любая реализация (написанная руками
или сгенерированная Jarvis-ом по этому шаблону) обязана ему соответствовать.

---

## 1. Стек

| Слой              | Решение                                       | Обоснование |
|-------------------|-----------------------------------------------|-------------|
| Язык              | Python **3.12** (`python:3.12-slim` в Docker) | требование владельца |
| Telegram          | `aiogram==3.13.*`                             | стабильная major на момент написания |
| FSM               | `MemoryStorage` (по умолчанию)                | для production переключаемо на `RedisStorage` через env |
| ORM               | `SQLAlchemy[asyncio]==2.0.*` + `aiosqlite`    | async-first; через ENV переключаемо на `asyncpg` (PostgreSQL) одной строкой |
| Миграции          | `alembic==1.13.*` (env `script_location=migrations`) | — |
| Scheduler         | `APScheduler==3.10.*` `AsyncIOScheduler` + `SQLAlchemyJobStore(url=DATABASE_URL)` | persistence напоминаний после рестарта |
| Конфиг            | `pydantic-settings==2.*` (`BaseSettings`)     | строгая типизация env |
| Логи              | `loguru==0.7.*`                               | _Проект 1 — loguru; Проект 2 переедет на structlog_ |
| Тесты             | `pytest==8.*` + `pytest-asyncio>=0.23` + `freezegun` | для time-sensitive scheduler-тестов |
| Линтеры           | `ruff` + `mypy --strict`                      | — |
| Деплой            | `Dockerfile` + `docker-compose.yml`           | Railway free tier |

---

## 2. Структура проекта

```
aiogram-booking/
├── bot/
│   ├── __init__.py
│   ├── main.py                 # entrypoint, регистрация роутеров и scheduler
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py            # /start, /help
│   │   ├── booking.py          # FSM-цепочка бронирования + /book
│   │   ├── my.py               # /my, отмена своих записей
│   │   └── admin.py            # /admin, /today, /tomorrow, /add_slot, /block_slot, /broadcast
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── client.py           # inline-меню клиента
│   │   └── admin.py            # admin-меню
│   ├── states.py               # BookingStates, AdminStates
│   ├── middlewares/
│   │   ├── __init__.py
│   │   ├── db.py               # инжектит async-сессию
│   │   └── admin.py            # фильтр прав
│   └── filters/
│       ├── __init__.py
│       └── is_admin.py
├── db/
│   ├── __init__.py
│   ├── models.py               # SQLAlchemy 2.x модели
│   ├── session.py              # async_engine + async_session_factory
│   └── repositories/
│       ├── __init__.py
│       ├── service.py
│       ├── master.py
│       ├── slot.py
│       ├── booking.py
│       └── client.py
├── services/
│   ├── __init__.py
│   ├── scheduler.py            # AsyncIOScheduler + 3 cron-job-а
│   ├── notifier.py             # отправка напоминаний клиенту
│   ├── slot_generator.py       # сидер + rolling window
│   └── phone.py                # normalize_phone()
├── seeders/
│   ├── __init__.py
│   └── demo_data.py            # 3 услуги, 2 мастера, 14 дней слотов
├── migrations/                 # alembic-окружение
│   ├── env.py
│   └── versions/
├── core/
│   ├── __init__.py
│   ├── config.py               # pydantic-settings
│   └── logging.py              # loguru-setup
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # async fixtures, in-memory db
│   ├── test_smoke.py
│   ├── test_phone.py
│   ├── test_booking_flow.py
│   ├── test_my_bookings.py
│   ├── test_admin_rights.py
│   ├── test_admin_today_tomorrow.py
│   ├── test_scheduler_rolling.py
│   ├── test_broadcast.py
│   └── test_repositories.py
├── docs/
│   └── architecture.mmd        # Mermaid-диаграмма
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml              # ruff + mypy + pytest конфиг в одном файле
├── requirements.txt
├── README.md
├── SPEC.md                     # этот файл
└── template.yaml               # kind: booking_bot
```

---

## 3. Модель данных

> SQLAlchemy 2.x, declarative с `MappedAsDataclass`. PK = `int` autoincrement
> кроме `Client.tg_user_id` — там natural key.

### `Service`
| поле          | тип        | nullable | примечание |
|---------------|------------|----------|------------|
| id            | INTEGER PK | no       | autoincrement |
| name          | TEXT       | no       | unique |
| duration_min  | INTEGER    | no       | длительность услуги |
| price_kop     | INTEGER    | no       | цена в копейках |
| is_active     | BOOLEAN    | no       | default true |

### `Master`
| поле            | тип        | nullable | примечание |
|-----------------|------------|----------|------------|
| id              | INTEGER PK | no       | autoincrement |
| name            | TEXT       | no       | |
| services_csv    | TEXT       | no       | csv `service.id`-ов которые умеет |
| schedule_json   | TEXT       | no       | json `{"mon":["10:00","20:00"], ...}` |
| is_active       | BOOLEAN    | no       | default true |

### `Slot`
| поле           | тип         | nullable | примечание |
|----------------|-------------|----------|------------|
| id             | INTEGER PK  | no       | |
| master_id      | INTEGER FK  | no       | → Master.id |
| service_id     | INTEGER FK  | no       | → Service.id |
| start_at       | DATETIME    | no       | UTC; индекс |
| end_at         | DATETIME    | no       | UTC |
| status         | TEXT        | no       | `available` / `booked` / `blocked`; default `available` |
| booking_id     | INTEGER FK  | yes      | → Booking.id (set при `booked`) |

Уникальный индекс `(master_id, start_at)` чтобы исключить дубль-слоты.

### `Booking`
| поле            | тип        | nullable | примечание |
|-----------------|------------|----------|------------|
| id              | INTEGER PK | no       | |
| slot_id         | INTEGER FK | no       | → Slot.id, unique |
| client_id       | INTEGER FK | no       | → Client.id |
| status          | TEXT       | no       | `active` / `cancelled` |
| created_at      | DATETIME   | no       | UTC, default `func.now()` |
| reminded_24h    | BOOLEAN    | no       | default false |
| reminded_2h     | BOOLEAN    | no       | default false |
| cancel_reason   | TEXT       | yes      | заполняется при отмене |

### `Client`
| поле          | тип            | nullable | примечание |
|---------------|----------------|----------|------------|
| id            | INTEGER PK     | no       | |
| tg_user_id    | BIGINT         | no       | unique |
| tg_username   | TEXT           | yes      | |
| full_name     | TEXT           | no       | |
| phone         | TEXT           | no       | формат `+7XXXXXXXXXX` |
| created_at    | DATETIME       | no       | default `func.now()` |

### `AdminLog`
| поле          | тип           | nullable | примечание |
|---------------|---------------|----------|------------|
| id            | INTEGER PK    | no       | |
| admin_tg_id   | BIGINT        | no       | |
| action        | TEXT          | no       | `add_slot` / `block_slot` / `broadcast` / ... |
| payload_json  | TEXT          | yes      | произвольный json |
| ts            | DATETIME      | no       | default `func.now()` |

---

## 4. FSM-граф бронирования

```
[Idle]
   │ /book или кнопка «Записаться»
   ▼
[BookingStates.choosing_service] ──── (inline_kb из активных Service) ───►
   │ ◄──[Назад/Отмена ⇒ Idle]
   ▼
[BookingStates.choosing_master] ──── (inline_kb из мастеров умеющих услугу) ───►
   ▼
[BookingStates.choosing_date] ─── (inline_kb с 14 ближайшими датами где есть available-слоты у мастера) ───►
   ▼
[BookingStates.choosing_slot] ─── (inline_kb со слотами на выбранную дату) ───►
   ▼
[BookingStates.entering_name] ─── (text input, валидация: 2..60 символов) ───►
   ▼
[BookingStates.entering_phone] ─── (text input, normalize_phone) ───►
   │ если не валиден ⇒ inline_kb «Введите номер в формате +7 905 123 45 67», состояние то же
   ▼
[BookingStates.confirm] ─── (inline_kb «Подтвердить» / «Отменить») ───►
   │ Подтвердить ⇒ транзакция: SELECT slot FOR UPDATE WHERE status='available' →
   │              UPDATE slot SET status='booked', booking_id=... → INSERT booking
   │              если slot уже booked другим — сообщить «Слот занят», вернуть в [choosing_slot]
   ▼
[Idle]  + сообщение «✅ Запись создана №<id>, ждём вас <date_time>» + scheduler-job-ы
```

Любое сообщение `/cancel` или кнопка «Отмена» сбрасывает состояние в `Idle`.

---

## 5. Команды

### Клиент

| Команда / Action | Описание |
|------------------|----------|
| `/start`         | Приветствие + inline-меню («Записаться», «Мои записи», «Помощь»). |
| `/book`          | Старт FSM бронирования. |
| `/my`            | Список активных записей клиента (карточка + inline «Отменить»). |
| `/cancel`        | Сбросить текущий FSM-state. |
| `/help`          | Справка. |

### Админ (только если `tg_user_id ∈ ADMIN_IDS`)

| Команда             | Описание |
|---------------------|----------|
| `/admin`            | Меню админки. |
| `/today`            | Список всех `active` записей на сегодня. |
| `/tomorrow`         | Список всех `active` записей на завтра. |
| `/add_slot`         | FSM добавления слота: мастер → услуга → дата → начало. Слот с `status='available'`. |
| `/block_slot`       | FSM: выбрать `available` слот → перевести в `blocked`. |
| `/broadcast`        | FSM: ввести текст → подтверждение → рассылка всем `Client`-ам с rate-limit 30 msg/sec. |

Не-админам команды отвечают «Команда недоступна».

Клиентский UX **не продвигает слэш-команды** в текстах: основной путь — inline-меню
и свободный текст/голос (NLU).

---

## 5.1 NLU, persona и голос (расширение шаблона)

| Компонент | Поведение |
|-----------|-----------|
| `ENABLE_NLU` | Свободный текст → `classify_intent` (Groq/Ollama). |
| `ENABLE_VOICE` | Голос → Groq Whisper (`GROQ_API_KEY` обязателен). |
| `AUTO_SEED_DEMO` | При пустой БД — `seeders.demo_data` (3 услуги, 2 мастера, 14 дней слотов). |
| Intents | `book`, `cancel`, `help`, `my`, `masters`, `smalltalk`, `other`. |
| `book` | Включает «когда свободен мастер» → реальные слоты из `SlotRepo`, не галлюцинации LLM. |
| `other` | Redirect на запись; FAQ только по явным вопросам (`SALON_BRANDS`, `PETS_ALLOWED`). |
| Persona | Короткие реплики администратора; FSM — шаблоны, LLM опционально для приветствия. |
| `services/service_aliases.py` | Разговорные синонимы услуг (напр. «френч» → «маникюр»). |
| `services/text_guard.py` | Пост-фильтр: без CJK, max длина ответа. |
| `CB_BACK` | Шаг назад в FSM (master → service, date → master, slot → date). |

Демо-мастера по умолчанию: **Анна**, **Дмитрий**. Услуги: **Стрижка**, **Маникюр**, **Массаж**.

### 5.2 Лимит сообщений (anti-abuse)

| ENV | По умолчанию | Смысл |
|-----|--------------|--------|
| `ENABLE_USAGE_LIMIT` | `true` | Включить middleware |
| `DAILY_MSG_LIMIT` | `100` | Макс. входящих действий/сутки на пользователя |
| `DAILY_MSG_STRIKES_BEFORE_BLOCK` | `3` | Сколько **разных дней** с превышением → блок |
| `SALON_ADMIN_CONTACT` | — | Контакт в тексте блокировки |

Сутки — календарный день в `TZ`. Считаются текст, голос, callback-кнопки. `ADMIN_IDS` не лимитируются.

Админ: `/unblock <tg_user_id>`, `/user_limit <tg_user_id>`.

---

## 6. Scheduler

`AsyncIOScheduler` инициализируется в `bot/main.py` после `Bot()`. JobStore =
`SQLAlchemyJobStore(url=settings.DATABASE_URL)` — задачи переживают рестарт.

### Job-ы

1. **`reminder_24h`** — `cron='*/15 * * * *'` (каждые 15 мин).
   - SELECT `Booking` WHERE status='active' AND `reminded_24h=False` AND
     slot.start_at BETWEEN now+23h AND now+24h.
   - Для каждого: отправить сообщение клиенту, set `reminded_24h=True`.

2. **`reminder_2h`** — `cron='*/5 * * * *'` (каждые 5 мин).
   - SELECT `Booking` WHERE status='active' AND `reminded_2h=False` AND
     slot.start_at BETWEEN now+1h45m AND now+2h.
   - Для каждого: отправить, set `reminded_2h=True`.

3. **`rolling_slots`** — `cron='0 3 * * *'` (каждый день в 03:00 локального TZ).
   - Для каждого активного `Master` догенерить слотов на день `now + 14d`,
     если их там ещё нет (idempotent через unique `(master_id, start_at)`).

4. **`cleanup_old_slots`** — `cron='0 4 * * 1'` (понедельник 04:00).
   - DELETE `Slot` WHERE start_at < now - 30d AND status != 'booked'.

### Graceful shutdown
По SIGTERM: `scheduler.shutdown(wait=True)`, `await dp.stop_polling()`,
`await bot.session.close()`. Это требование ТЗ для всех проектов.

---

## 7. Валидация телефона

`services/phone.py`:

```python
PHONE_RE = re.compile(r"^\+7(9\d{9})$")

def normalize_phone(raw: str) -> str | None:
    """Возвращает нормализованный +7XXXXXXXXXX или None."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-().·\u00A0]", "", raw)
    if cleaned.startswith("+7"):
        digits = cleaned[2:]
    elif cleaned.startswith(("8", "7")):
        digits = cleaned[1:]
    else:
        return None
    if len(digits) != 10 or not digits.isdigit():
        return None
    if digits[0] != "9":           # только мобильные
        return None
    return "+7" + digits
```

При ошибке отправлять клиенту:
> `Введите номер в формате +7 905 123 45 67`

Тесты: `test_phone.py` параметризован — валидные `+79051234567`,
`8 905 123-45-67`, `7(905)1234567`; невалидные `+7495...` (не моб),
`12345`, `""`, `"abcd"`.

---

## 8. Сидер mock-данных

`seeders/demo_data.py`. Запускается через CLI:
```bash
python -m seeders.demo_data
```

Заполняет:
- **Услуги**: «Стрижка» (60 мин, 150000), «Окрашивание» (180 мин, 450000), «Маникюр» (90 мин, 200000).
- **Мастера**:
  - Анна — стрижка + окрашивание; пн–пт 10:00–20:00; сб–вс выходные.
  - Мария — стрижка + маникюр; вт–сб 11:00–21:00; пн+вс выходные.
- **Слоты**: на 14 дней вперёд, шаг 60 мин по расписанию мастера, услуга по умолчанию = первая из его `services_csv` (для overrided слотов админ может задать другую).

Сидер идемпотентный: если услуга/мастер уже есть — пропускает.

---

## 9. Тесты (pytest, ≥ 8 файлов)

| Файл                        | Покрывает                                                     | Минимум |
|-----------------------------|---------------------------------------------------------------|---------|
| `test_smoke.py`             | импорты пакета, `core.config.Settings` загружается из `.env.example` | 2 |
| `test_phone.py`             | `normalize_phone` (параметризован, ≥ 12 кейсов)                | 12 |
| `test_booking_flow.py`      | happy path FSM-бронирования + race на одном слоте              | 4 |
| `test_my_bookings.py`       | `/my` показывает только активные текущего клиента, отмена      | 3 |
| `test_admin_rights.py`      | `is_admin`-фильтр; неадмин получает «Команда недоступна»       | 3 |
| `test_admin_today_tomorrow.py` | `/today` и `/tomorrow` корректно фильтруют по дате          | 4 |
| `test_scheduler_rolling.py` | `rolling_slots` job догенеривает только день +14, идемпотентен | 3 |
| `test_broadcast.py`         | `/broadcast` шлёт всем активным клиентам, пишет в `AdminLog`   | 3 |
| `test_repositories.py`      | базовые CRUD-методы каждого репозитория                        | 6 |

Все тесты — async (`pytest-asyncio`, `mode=auto`); БД in-memory SQLite
(`sqlite+aiosqlite:///:memory:`); фикстура `client` мокает `Bot` через
`AiogramTestSession`.

`freezegun.freeze_time` используется в `test_scheduler_rolling.py` и
`test_admin_today_tomorrow.py`.

**Цель**: минимум 38 ассертов, в текущем сборе ≥ 40 passed.

---

## 10. ENV-переменные

`.env.example`:

```ini
# Telegram
BOT_TOKEN=ставится при деплое
ADMIN_IDS=123456789,987654321
TZ=Europe/Moscow

# Database (SQLite по умолчанию; для PG: postgresql+asyncpg://user:pass@host/db)
DATABASE_URL=sqlite+aiosqlite:///./data/booking.db

# FSM Storage (memory|redis)
FSM_BACKEND=memory
REDIS_URL=

# Scheduler offsets (в минутах; полезно для тестов)
REMINDER_OFFSET_24H_MIN=1440
REMINDER_OFFSET_2H_MIN=120
ROLLING_HOUR_LOCAL=3

# Logging
LOG_LEVEL=INFO
LOG_JSON=false        # для production переключаем в true
```

Все ENV типизированы через `pydantic-settings.BaseSettings`. Отсутствие
обязательного `BOT_TOKEN` или пустые `ADMIN_IDS` → exit с кодом 2 и
понятным сообщением (а не traceback).

---

## 11. Docker

`Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends curl tini && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import sqlite3, sys; sqlite3.connect('data/booking.db').execute('SELECT 1'); sys.exit(0)" || exit 1
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "bot.main"]
```

`docker-compose.yml`:
```yaml
version: "3.9"
services:
  bot:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

---

## 12. Стандарты репо

- `.gitignore`: стандартный python-gitignore + `.env`, `.env.local`, `data/`, `*.db`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`.
- `pyproject.toml` с разделами `[tool.ruff]`, `[tool.mypy]` (strict), `[tool.pytest.ini_options]` (asyncio_mode="auto").
- Pre-commit-hooks: `ruff`, `mypy`, `pytest -k 'not slow'` на staged.
- GitHub Actions `.github/workflows/ci.yml`: lint + mypy + pytest + coverage upload (без actions-secret-required-features в шаблоне).
- LICENSE: MIT, copyright `s4s4s4s`.
- README по канону: что/зачем/стек/локально/Railway-deploy/архитектура (Mermaid)/MIT.

---

## 13. Контракт `template.yaml`

```yaml
slug: aiogram-booking
kind: booking_bot
entry_point: bot/main.py
test_command: pytest tests/ -v --asyncio-mode=auto
required_exports:
  - bot.main:main
  - services.phone:normalize_phone
  - db.session:get_session
required_signatures:
  - "services.phone:normalize_phone(raw: str) -> str | None"
  - "db.session:get_session() -> AsyncIterator[AsyncSession]"
description: |
  Универсальный бот записи клиентов: услуги, мастера, слоты,
  напоминания, админ-команды. Адаптируется под beauty-салон,
  клинику, барбершоп, автосервис, репетитора.
```

---

## 14. Что вне скоупа Проекта 1 (но точка расширения заложена)

- **Платежи**: предусмотрен метод `Booking.mark_paid()` и поле в модели `Service.requires_prepayment` (зарезервировано), но обработчиков нет.
- **CRM-интеграции** (Bizon365, AmoCRM): в `services/integrations/` оставить пустой `__init__.py` + ABC `CRMSync` для будущей реализации.
- **Мульти-локация**: в модели `Master` добавить опциональное поле `location_id` (nullable), которое сейчас игнорируется.
- **Push / Email**: только Telegram-нотификации.

---

## 15. Acceptance criteria шаблона

1. `pytest tests/ -v --asyncio-mode=auto` — **зелёный**, ≥ 40 passed.
2. `ruff check .` — **0 ошибок**.
3. `mypy --strict bot/ db/ services/ core/ seeders/` — **0 ошибок**.
4. `docker compose build` собирается без warnings.
5. `python -m seeders.demo_data` идемпотентен: дважды запустился → данные не задвоились.
6. `template.yaml` валиден; `_audit_template_hints.py` и `_audit_template_consistency.py` — `OK`.
7. SPEC ↔ код консистентны: каждый раздел SPEC имеет реализацию.
