# Деплой на Fly.io

> Цель: получить публично работающего бота на Fly.io (free tier) за
> 5–10 минут. Long-polling, без HTTP-сервера, с volume под SQLite.

## Шаг 1. Регистрация и установка flyctl

1. https://fly.io/app/sign-up — регистрируйся через GitHub.
2. Привязать карту (Fly требует card даже для free tier — это защита
   от ботов; деньги не списываются если не выходишь за лимиты).
3. Установить `flyctl` (Windows PowerShell):
   ```powershell
   iwr https://fly.io/install.ps1 -useb | iex
   ```
   Закрой и открой заново PowerShell, чтобы PATH обновился.
4. `fly auth login` — откроется браузер, авторизация в один клик.

## Шаг 2. Создать volume для SQLite

Volume — отдельный объект на Fly, он привязан к региону (у нас `fra`):

```powershell
fly volume create data --region fra --size 1 --yes
```

(размер `1` GB на старт; можно расширить позже без миграций).

## Шаг 3. Засекретить токен

ENV-переменные с секретами в Fly идут через `fly secrets`, а не через
`fly.toml` (иначе они попали бы в git):

```powershell
fly secrets set BOT_TOKEN="<your-token>" ADMIN_IDS="<your-user-id>"
```

## Шаг 4. Деплой

```powershell
fly deploy
```

Fly прочитает `fly.toml`, соберёт Docker-образ, поднимет одну VM в
Frankfurt, примонтирует volume `data` к `/app/data`. После `Deployed`
бот живой.

## Шаг 5. Сидер (один раз)

```powershell
fly ssh console --command "python -m seeders.demo_data"
```

Заполнит БД услугами, мастерами и слотами на 14 дней.

## Шаг 6. Проверка

В Telegram → твоему боту → `/start`. Должно прийти приветствие с
кнопками. Если что-то пошло не так:

```powershell
fly logs            # стрим логов
fly status          # состояние VM
fly ssh console     # зайти на машину
```

## Полезные команды

| Что | Команда |
|---|---|
| Посмотреть приложения | `fly apps list` |
| Подключиться к ssh | `fly ssh console` |
| Стрим логов | `fly logs` |
| Перезапуск | `fly machine restart <id>` |
| Изменить ресурсы | `fly scale memory 512` |
| Удалить app полностью | `fly apps destroy <name>` |

## Стоимость

Free tier (на момент 2026):
- 3× `shared-cpu-1x@256mb` VM навсегда бесплатно;
- 3 GB суммарных volumes;
- 160 GB исходящего трафика/мес.

Один booking-бот = 1 VM + 1 GB volume → бесплатно навсегда. Если
понадобится 512 MB RAM (например, при включении Redis-FSM) — тариф
переключится на pay-as-you-go (~$2–3/мес).

## Если переходим на PostgreSQL

```powershell
fly postgres create --name booking-db --region fra --vm-size shared-cpu-1x --volume-size 1
fly postgres attach booking-db --app polyakov-booking-demo
```

Fly автоматически выставит `DATABASE_URL` в формате
`postgres://...`. В нашем шаблоне нужно поменять схему на
`postgresql+asyncpg://`:

```powershell
fly secrets set DATABASE_URL="postgresql+asyncpg://<user>:<pass>@<host>/<db>"
```
