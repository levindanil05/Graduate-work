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
| **web** | Gunicorn, миграции и `collectstatic` при старте (`deploy/entrypoint.sh`) |
| **db** | PostgreSQL 16 |
| **worker** | Цикл: `run_external_sync_worker --once`, `purge_trashed`, `purge_storage_shares`, пауза |
| **backup** | Периодический `pg_dump` в том `postgres_backups` |

Тома: `userfiles`, `staticfiles`, `postgres_data`, `postgres_backups`.

## Хранилище файлов

Основное хранилище файлов редакций задаётся окружением `STORAGE_BACKEND`:

- `local` (по умолчанию) — каталог `USERFILES_ROOT` (том `userfiles` в compose);
- `nextcloud` — WebDAV Nextcloud (отдельный пользователь и папка только для программы).

Пошаговая настройка Nextcloud, пароль приложения, проверка `curl` и команда
`manage.py check_nextcloud` — в [`nextcloud-setup.md`](nextcloud-setup.md).
Все переменные с пояснениями — в `.env.example`.

### Переход с локальной папки на Nextcloud

1. Подготовьте пользователя и папку в Nextcloud, заполните `NEXTCLOUD_*` в `.env`
   (пока можно оставить `STORAGE_BACKEND=local`).
2. Проверьте: `python manage.py check_nextcloud`.
3. Перенесите файлы (ключи в БД не меняются):

```bash
python manage.py migrate_storage_backend --from local --to nextcloud --verify
```

Повторный запуск безопасен: уже перенесённые файлы пропускаются.
`--delete-source` удаляет локальные копии только вместе с `--verify`.

4. Поставьте `STORAGE_BACKEND=nextcloud`, перезапустите `web` и `worker`.
5. `/healthz` должен показывать `storage: ok` и `storage_backend: nextcloud`.

При `nextcloud` резервное копирование **файлов редакций** делает администрация
на стороне Nextcloud. Том `userfiles` по-прежнему нужен для временных файлов
(загрузка, proxy-скачивание, выгрузка на Яндекс.Диск).

Яндекс.Диск остаётся **резервной публикацией утверждённых** редакций и не заменяет
основное хранилище — см. [external-storage-sync.md](external-storage-sync.md).

## Переменные окружения

Основные переменные перечислены в `.env.example`. Обязательные для продакшена:

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`
- `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL` (в compose указывает на сервис `db`)
- `USERFILES_ROOT`, `STATIC_ROOT`
- При `STORAGE_BACKEND=nextcloud`: `NEXTCLOUD_URL`, `NEXTCLOUD_USER`, `NEXTCLOUD_APP_PASSWORD`
- Токены Яндекс.Диска для подключений (`YANDEX_DISK_*`)
- `TRASH_RETENTION_DAYS` — срок хранения в корзине до автоудаления

`COLLECT_STATIC_AT_START=0` отключает сбор статики при каждом рестарте web/worker.

## Резервное копирование и восстановление

- Бэкапы БД пишет сервис **backup** в том `postgres_backups` (`BACKUP_INTERVAL_SECONDS`, `BACKUP_KEEP_COUNT`).
- Файлы планов:
  - при `STORAGE_BACKEND=local` — каталог **userfiles**; включите его в регламент хоста;
  - при `STORAGE_BACKEND=nextcloud` — бэкап папки программы в Nextcloud (плюс том `userfiles` для временных файлов).
- Восстановление БД (пример): остановить `web`/`worker`, выполнить `pg_restore` в `db`, поднять сервисы снова.

## Обновление и откат

**Обновление:**

```bash
git pull
docker compose build web worker
docker compose up -d
```

Миграции применяются при старте контейнеров.

**Откат:** вернуть предыдущий образ/коммит, `docker compose up -d`, при необходимости восстановить БД из бэкапа. Том `userfiles` (и данные в Nextcloud) не откатываются автоматически — храните снапшоты.

## Healthz

Эндпоинт `/healthz` проверяет БД и хранилище:

- `local` — запись/удаление пробного файла в `USERFILES_ROOT`;
- `nextcloud` — запись/чтение/удаление пробного файла в папке программы.

В публичном nginx доступ с интернета обычно **закрыт** (см. `plans.conf`); для мониторинга используйте localhost или внутреннюю сеть.

## Обратная связь и справка

В интерфейсе: раздел **Обратная связь** (`/feedback/`) — сообщения пользователей для администраторов; **Справка** (`/help/`) — инструкции и глоссарий. После развёртывания проверьте, что пользователи с ролью администратора видят очередь обращений в шапке сайта.
