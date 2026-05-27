# Деплой на Railway

> Цель: получить публично работающего бота на Railway free tier за
> 10–15 минут. Лимит free tier — 500 часов/мес и 1 GB RAM достаточно
> для одного booking-бота.

## Шаг 1. Telegram

1. Открыть [@BotFather](https://t.me/BotFather), `/newbot`.
2. Указать имя и username (заканчивается на `_bot`).
3. Скопировать токен (формат `1234567890:AAH...`). **НИКОГДА не коммить**
   токен в git.
4. У [@userinfobot](https://t.me/userinfobot) узнать свой Telegram user-id.

## Шаг 2. GitHub

```bash
cd c:\projects\portfolio-bot-record
git init
git add .
git commit -m "init: aiogram-booking deploy"
git remote add origin https://github.com/<your-user>/portfolio-bot-record.git
git push -u origin main
```

Если репо приватный — нужен PAT (Personal Access Token) с правом `repo`.
Создаётся в `Settings → Developer settings → Personal access tokens → Tokens (classic)`.

## Шаг 3. Railway

1. [railway.app](https://railway.app) → **New Project** → **Deploy from
   GitHub repo** → выбрать репозиторий.
2. Railway автоматически использует `Dockerfile`. Билд пойдёт сразу.
3. **Variables** (вкладка):
   ```
   BOT_TOKEN=<токен из BotFather>
   ADMIN_IDS=<ваш user-id>
   TZ=Europe/Moscow
   DATABASE_URL=sqlite+aiosqlite:///./data/booking.db
   LOG_LEVEL=INFO
   LOG_JSON=true
   ```
4. **Settings → Volumes**: добавить volume `data` mount-path
   `/app/data` (чтобы SQLite-файл не пропадал при пересборке).
5. Дождаться `Deployment Live`.

## Шаг 4. Сидер в проде

Один раз после первого деплоя — выполнить:
```
railway run python -m seeders.demo_data
```

(или зайти в Railway shell и запустить ту же команду).

## Шаг 5. Проверка

В Telegram: `/start` боту. Должно прийти приветствие с кнопками
«Записаться / Мои записи / Помощь».

Если что-то сломалось — Railway → **Deployments → Logs**. Бот логирует
структурно (LOG_JSON=true) — ошибки видны мгновенно.

## Если переходим на Postgres

Railway → **+ New** → **Database** → **Add PostgreSQL**. После
поднятия БД — скопировать `DATABASE_URL` из вкладки `Connect`. Заменить
схему `postgresql://` на `postgresql+asyncpg://` и положить в
ENV-переменную бота. Перезапустить.

## Стоимость

Free tier: 500 часов/мес. Один бот ≈ 720 часов/мес → нужен `Hobby plan`
($5/мес) если хотим круглосуточно. До этого — спать по cron'у в часы
неактивности.
