# Развёртывание (Docker Compose + хостовой nginx)

Сервис рассчитан на работу **за существующим nginx с TLS**: контейнер `web` слушает только `127.0.0.1:8000`, сертификаты и публичный HTTP(S) настраиваются на хосте. Пример блока `server` — [`deploy/nginx/plans.conf`](../deploy/nginx/plans.conf).

## Быстрый старт

1. Скопируйте [`src/education_site/.env.example`](../src/education_site/.env.example) в корень репозитория как `.env` и задайте как минимум `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`.
2. Соберите и поднимите стек:

```bash
docker compose build
docker compose up -d
```

3. Подключите `plans.conf` к nginx, укажите `alias` для `/static/` на каталог `staticfiles` (том Docker или синхронизированная копия после `collectstatic`).
4. Проверка (только с хоста, см. nginx): `curl -sS http://127.0.0.1:8000/healthz`

## Сервисы compose

| Сервис | Назначение |
|--------|------------|
| **web** | Gunicorn, миграции и `collectstatic` при старте (`deploy/entrypoint.sh`) |
| **db** | PostgreSQL 16 |
| **worker** | Цикл: `run_external_sync_worker --once`, `purge_trashed`, пауза |
| **backup** | Периодический `pg_dump` в том `postgres_backups` |

Тома: `userfiles`, `staticfiles`, `postgres_data`, `postgres_backups`.

## Переменные окружения

Основные переменные перечислены в `.env.example`. Обязательные для продакшена:

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`
- `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL` (в compose указывает на сервис `db`)
- `USERFILES_ROOT`, `STATIC_ROOT`
- Токены Яндекс.Диска для подключений (`YANDEX_DISK_*`)
- `TRASH_RETENTION_DAYS` — срок хранения в корзине до автоудаления

`COLLECT_STATIC_AT_START=0` отключает сбор статики при каждом рестарте web/worker.

## Резервное копирование и восстановление

- Бэкапы БД пишет сервис **backup** в том `postgres_backups` (`BACKUP_INTERVAL_SECONDS`, `BACKUP_KEEP_COUNT`).
- Файлы планов — каталог **userfiles**; включите его в регламент резервного копирования хоста.
- Восстановление БД (пример): остановить `web`/`worker`, выполнить `pg_restore` в `db`, поднять сервисы снова.

## Обновление и откат

**Обновление:**

```bash
git pull
docker compose build web worker
docker compose up -d
```

Миграции применяются при старте контейнеров.

**Откат:** вернуть предыдущий образ/коммит, `docker compose up -d`, при необходимости восстановить БД из бэкапа. Том `userfiles` не откатывается автоматически — храните снапшоты.

## Healthz

Эндпоинт `/healthz` проверяет БД и доступность каталога userfiles. В публичном nginx доступ с интернета обычно **закрыт** (см. `plans.conf`); для мониторинга используйте localhost или внутреннюю сеть.

## Обратная связь и справка

В интерфейсе: раздел **Обратная связь** (`/feedback/`) — сообщения пользователей для администраторов; **Справка** (`/help/`) — инструкции и глоссарий. После развёртывания проверьте, что пользователи с ролью администратора видят очередь обращений в шапке сайта.
