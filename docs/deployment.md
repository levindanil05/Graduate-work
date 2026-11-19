# Развёртывание (Docker Compose + хостовой nginx)

Сервис рассчитан на работу **за существующим nginx с TLS**: контейнер `web` слушает
только `127.0.0.1:${WEB_PORT}` (на сервере umu — **8006**), сертификаты и публичный
HTTP(S) настраиваются на хосте. Пример блока `server` — [`deploy/nginx/plans.conf`](../deploy/nginx/plans.conf).

Домен: **plx.vstu.ru**. Каталог на сервере: `/containers/vstuplans/` (или аналог).

Код приложения живёт **внутри Docker-образа**. Обновление — через git tag и пересборку
образа, а не через общую папку с кодом (см. раздел «Релиз и откат»).

## Быстрый старт

1. Скопируйте [`src/vstuplans/.env.example`](../src/vstuplans/.env.example) в корень
   репозитория как `.env` и задайте как минимум:
   - `DJANGO_SECRET_KEY`
   - `POSTGRES_PASSWORD` (пароль роли `vstuplans`)
   - `DATABASE_URL` (тот же пароль, хост `pg-shared`)
   - `DJANGO_ALLOWED_HOSTS=plx.vstu.ru`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://plx.vstu.ru`
   - `WEB_PORT=8006`
2. Убедитесь, что внешняя Docker-сеть `pg_vstuplans` существует и Postgres доступен
   (см. «Подключение к общему Postgres»).
3. Соберите и поднимите стек (оверлей публикует Gunicorn на `127.0.0.1:${WEB_PORT}`):

```bash
docker compose -f docker-compose.yml -f docker-compose.host.yml build
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d
```

4. Подключите [`deploy/nginx/plans.conf`](../deploy/nginx/plans.conf) к хостовому nginx
   (`server_name plx.vstu.ru`, upstream `127.0.0.1:8006`).
5. Выпустите сертификат: `sudo certbot --nginx -d plx.vstu.ru`.
6. Проверка с хоста: `curl -sS http://127.0.0.1:8006/healthz`

## Сервисы compose

| Сервис | Назначение |
|--------|------------|
| **web** | Gunicorn; при старте ждёт БД, применяет миграции и `collectstatic` (`deploy/entrypoint.sh`) |
| **worker** | Цикл: `run_external_sync_worker --once`, `purge_trashed`, `purge_storage_shares`; стартует после `web` healthy |
| **backup** | Периодический `pg_dump -Fc` в том `postgres_backups` (образ `postgres:18-alpine`) |

Собственного сервиса `db` нет: используется общий Postgres (vstu_schedule).

Тома: `userfiles`, `staticfiles`, `postgres_backups`.

Сеть: `pg_vstuplans` (external) — для доступа к БД по имени `pg-shared`.

## Подключение к общему Postgres

На сервере umu Postgres крутится в контейнере `vstu_schedule-db-1` (PostgreSQL 18),
порт 5432 наружу не опубликован. Для нашего приложения:

1. Сеть (один раз):

```bash
docker network create pg_vstuplans
docker network connect --alias pg-shared pg_vstuplans vstu_schedule-db-1
```

2. Роль и БД (от суперпользователя `vstusched` в их контейнере):

```bash
cd /containers/vstusched/vstu_schedule
PW=$(openssl rand -hex 24); echo "$PW"
docker compose exec -T db psql -U vstusched -d postgres -v ON_ERROR_STOP=1 <<SQL
CREATE ROLE vstuplans LOGIN PASSWORD '$PW';
CREATE DATABASE vstuplans OWNER vstuplans ENCODING 'UTF8';
REVOKE CONNECT ON DATABASE vstuplans FROM PUBLIC;
REVOKE CONNECT ON DATABASE vstuschedule FROM PUBLIC;
SQL
```

3. Чтобы сеть не отваливалась при пересоздании контейнера БД, в
   `docker-compose.yml` проекта vstu_schedule у сервиса `db`:

```yaml
services:
  db:
    # ... существующее ...
    networks:
      default: {}
      pg_vstuplans:
        aliases: [pg-shared]

networks:
  pg_vstuplans:
    external: true
```

Строка `default: {}` обязательна, иначе `db` выпадет из сети самого vstu_schedule.

4. В `.env` нашего проекта:

```env
DATABASE_URL=postgresql://vstuplans:<пароль>@pg-shared:5432/vstuplans
POSTGRES_USER=vstuplans
POSTGRES_PASSWORD=<пароль>
POSTGRES_DB=vstuplans
PGHOST=pg-shared
```

Проверка:

```bash
docker run --rm --network pg_vstuplans -e PGPASSWORD='...' postgres:18-alpine \
  psql -h pg-shared -U vstuplans -d vstuplans -c 'select current_user, version();'
```

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
- `DATABASE_URL` (хост `pg-shared` в сети `pg_vstuplans`)
- `POSTGRES_PASSWORD`, `WEB_PORT`
- `USERFILES_ROOT`, `STATIC_ROOT`
- При `STORAGE_BACKEND=nextcloud`: `NEXTCLOUD_URL`, `NEXTCLOUD_USER`, `NEXTCLOUD_APP_PASSWORD`
- Токены Яндекс.Диска для подключений (`YANDEX_DISK_*`)
- `TRASH_RETENTION_DAYS` — срок хранения в корзине до автоудаления
- `APP_VERSION` — тег образа `vstuplans:${APP_VERSION}`

`COLLECT_STATIC_AT_START=0` отключает сбор статики при каждом рестарте web
(только при запуске gunicorn; worker миграции и статику не трогает).

Статику в проде отдаёт **WhiteNoise** из приложения; отдельный `location /static/`
в nginx не требуется.

## Резервное копирование и восстановление

- Бэкапы БД пишет сервис **backup** в том `postgres_backups`
  (`BACKUP_INTERVAL_SECONDS`, `BACKUP_KEEP_COUNT`), файлы `*.dump` (формат `pg_dump -Fc`).
- Файлы планов:
  - при `STORAGE_BACKEND=local` — каталог **userfiles**; включите его в регламент хоста;
  - при `STORAGE_BACKEND=nextcloud` — бэкап папки программы в Nextcloud (плюс том `userfiles` для временных файлов).
- Восстановление БД (пример): остановить `web`/`worker`, выполнить
  `pg_restore` в контейнер backup или через сеть `pg_vstuplans`, поднять сервисы снова.

## Релиз и откат

Код в образе; на сервере не монтируйте исходники в контейнер.

**Обновление:**

```bash
git fetch --tags
git checkout v1.1.0          # или: git pull на нужной ветке
# APP_VERSION в .env должен совпадать с тегом (без префикса v)
docker compose -f docker-compose.yml -f docker-compose.host.yml build web worker
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d
```

Миграции применяет только `web` при старте gunicorn.

**Откат:** `git checkout` предыдущего тега, `docker compose build` (или
`APP_VERSION=1.0.0 docker compose up -d`, если образ ещё локально), при
несовместимых миграциях — восстановить БД из бэкапа. Том `userfiles` (и данные
в Nextcloud) не откатываются автоматически.

Позже (несколько серверов / запрет сборки на проде): собирать образ в CI и
публиковать в реестр; на сервере только `docker compose pull && up -d`.

## Healthz

Эндпоинт `/healthz` проверяет БД и хранилище:

- `local` — запись/удаление пробного файла в `USERFILES_ROOT`;
- `nextcloud` — запись/чтение/удаление пробного файла в папке программы.

В публичном nginx доступ с интернета **закрыт** (см. `plans.conf`); для мониторинга
используйте localhost или внутреннюю сеть.

## Чек-лист перед продакшеном

- [ ] `DJANGO_DEBUG=0`, надёжный `DJANGO_SECRET_KEY`
- [ ] `DJANGO_ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` = `plx.vstu.ru` / `https://plx.vstu.ru`
- [ ] Нет bind-mount кода (`.:/app`) и нет `--reload` у gunicorn
- [ ] Сеть `pg_vstuplans`, роль/БД `vstuplans`, `DATABASE_URL` на `pg-shared`
- [ ] `WEB_PORT=8006`, nginx upstream совпадает
- [ ] Certbot для `plx.vstu.ru`
- [ ] В compose vstu_schedule сохранена сеть `pg_vstuplans` у `db`
- [ ] Бэкапы: том `postgres_backups` + регламент для `userfiles` / Nextcloud

## Обратная связь и справка

В интерфейсе: раздел **Обратная связь** (`/feedback/`) — сообщения пользователей для
администраторов; **Справка** (`/help/`) — инструкции и глоссарий. После развёртывания
проверьте, что пользователи с ролью администратора видят очередь обращений в шапке сайта.
