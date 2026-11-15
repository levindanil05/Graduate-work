# Подключение основного хранилища к Nextcloud

Пошаговая инструкция для локальной проверки с реальным Nextcloud и для сервера.
Основное хранилище файлов редакций может быть локальной папкой (`STORAGE_BACKEND=local`)
или Nextcloud (`STORAGE_BACKEND=nextcloud`). Резервная публикация на Яндекс.Диск
не заменяется: см. [external-storage-sync.md](external-storage-sync.md).

Переменные окружения описаны в [`src/education_site/.env.example`](../src/education_site/.env.example).

---

## 1. Пользователь для программы

1. Войдите в Nextcloud под администратором.
2. Откройте **Пользователи** (или **Параметры пользователей**).
3. Создайте пользователя, например `plans-app`.
   - Права администратора **не нужны**.
   - Квота — с запасом под все редакции (десятки–сотни МБ на план).
4. Запомните **логин** (не отображаемое имя). Его пишите в `NEXTCLOUD_USER`.

---

## 2. Папка программы

1. Войдите в Nextcloud **под созданным пользователем**.
2. Создайте папку, например `plans` (или `education-site`).
3. Убедитесь, что папку **не** расшарили другим пользователям.
4. Это значение без ведущего `/` пишите в `NEXTCLOUD_ROOT` (пример: `plans`).

Если папку создаёт администратор и отдаёт пользователю общим доступом:
нужно право **Редактирование**, и пользователь должен **принять** общий доступ.
Предпочтительнее, чтобы папка лежала в собственных файлах пользователя программы.

---

## 3. Пароль приложения

Обычный пароль учётной записи для WebDAV часто запрещён. Нужен **пароль приложения**.

1. Войдите под пользователем программы.
2. Откройте **Параметры** → **Безопасность**.
3. Раздел **Устройства и сеансы** → **Создать пароль приложения**.
4. Имя, например `education-site`.
5. Скопируйте показанный пароль сразу: повторно его увидеть нельзя.
6. Его пишите в `NEXTCLOUD_APP_PASSWORD` (не пароль входа в веб-интерфейс).

---

## 4. Адрес WebDAV

1. В веб-интерфейсе откройте **Файлы**.
2. Внизу слева — **Параметры**.
3. Поле **WebDAV** вида:

   `https://cloud.example.edu/remote.php/dav/files/plans-app/`

Из него:

| Часть адреса | Переменная |
|---|---|
| Всё **до** `/remote.php` (без завершающего `/`) | `NEXTCLOUD_URL` → `https://cloud.example.edu` |
| Последний сегмент пути (`plans-app`) | `NEXTCLOUD_USER` |

Если Nextcloud в подкаталоге (`https://example.edu/nextcloud/...`), то
`NEXTCLOUD_URL=https://example.edu/nextcloud`.

`NEXTCLOUD_PUBLIC_URL` нужен только когда программа ходит по **внутреннему**
адресу (docker / localhost), а пользователю нужна ссылка с **публичного**
HTTPS. Если пусто — берётся `NEXTCLOUD_URL`.

---

## 5. Публичные ссылки (для режима `direct`)

Администратор Nextcloud:

1. **Параметры администрирования** → **Общий доступ**.
2. Включите **Разрешить пользователям делиться через публичные ссылки**.
3. Если задан принудительный срок действия ссылок, максимум должен быть
   **не меньше 7 дней** (или уменьшите `NEXTCLOUD_SHARE_TTL_DAYS`).
4. **Разрешить публичную загрузку** не нужно.

Ссылки создаёт только программа, на отдельные файлы, со сроком до 7 дней.
Папку `NEXTCLOUD_ROOT` целиком делать публичной **нельзя**.

---

## 6. Проверка вручную (`curl`)

Подставьте свои значения. В `cmd` на Windows удобен `curl.exe`.

Переменные для примеров:

```text
NC_URL=https://cloud.example.edu
NC_USER=plans-app
NC_PASS=xxxx-xxxx-xxxx-xxxx
NC_ROOT=plans
```

### 6.1. Вход и список корня пользователя (ожидается 207)

```bash
curl.exe -sS -o NUL -w "%{http_code}" -u "%NC_USER%:%NC_PASS%" -X PROPFIND -H "Depth: 0" "%NC_URL%/remote.php/dav/files/%NC_USER%/"
```

### 6.2. Папка программы (ожидается 207; если 404 — создайте папку в веб-интерфейсе)

```bash
curl.exe -sS -o NUL -w "%{http_code}" -u "%NC_USER%:%NC_PASS%" -X PROPFIND -H "Depth: 0" "%NC_URL%/remote.php/dav/files/%NC_USER%/%NC_ROOT%"
```

### 6.3. Пробный файл (201 или 204)

```bash
echo check > check.txt
curl.exe -sS -o NUL -w "%{http_code}" -u "%NC_USER%:%NC_PASS%" -X PUT --data-binary "@check.txt" "%NC_URL%/remote.php/dav/files/%NC_USER%/%NC_ROOT%/_check/check.txt"
```

Если 409 на каталог `_check`, сначала:

```bash
curl.exe -sS -o NUL -w "%{http_code}" -u "%NC_USER%:%NC_PASS%" -X MKCOL "%NC_URL%/remote.php/dav/files/%NC_USER%/%NC_ROOT%/_check"
```

### 6.4. Чтение (200) и публичная ссылка

```bash
curl.exe -sS -u "%NC_USER%:%NC_PASS%" "%NC_URL%/remote.php/dav/files/%NC_USER%/%NC_ROOT%/_check/check.txt"
```

Создание ссылки (в ответе XML/JSON будет `token` и `id`):

```bash
curl.exe -sS -u "%NC_USER%:%NC_PASS%" -H "OCS-APIRequest: true" -H "Content-Type: application/x-www-form-urlencoded" -d "path=/%NC_ROOT%/_check/check.txt&shareType=3&permissions=1" "%NC_URL%/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json"
```

Открытие (подставьте `TOKEN`):

```bash
curl.exe -sS -o NUL -w "%{http_code}" -L "%NC_URL%/s/TOKEN/download"
curl.exe -sS -o NUL -w "%{http_code}" -L "%NC_URL%/s/TOKEN/download/check.txt"
```

Ожидается 200. Второй вариант с именем файла предпочтителен для кнопки «Скачать».

### 6.5. Удаление пробных данных

```bash
curl.exe -sS -u "%NC_USER%:%NC_PASS%" -H "OCS-APIRequest: true" -X DELETE "%NC_URL%/ocs/v2.php/apps/files_sharing/api/v1/shares/SHARE_ID"
curl.exe -sS -u "%NC_USER%:%NC_PASS%" -X DELETE "%NC_URL%/remote.php/dav/files/%NC_USER%/%NC_ROOT%/_check/check.txt"
curl.exe -sS -u "%NC_USER%:%NC_PASS%" -X DELETE "%NC_URL%/remote.php/dav/files/%NC_USER%/%NC_ROOT%/_check"
```

### Частые ошибки

| Код / симптом | Что проверить |
|---|---|
| 401 | Логин, **пароль приложения** (не пароль веб-входа), пользователь не заблокирован |
| 403 | Запрещены публичные ссылки; слишком большой `expireDate`; нет права на путь |
| 404 | Неверный `NEXTCLOUD_URL` / `NEXTCLOUD_ROOT` / логин в пути WebDAV |
| 405 / 412 / 423 | Конфликт имени, блокировка файла, метод запрещён на этом URL |
| Ошибка сертификата | Для самоподписи временно `NEXTCLOUD_VERIFY_TLS=false` только на проверке; в работе — нормальный сертификат или путь к CA |

---

## 7. Настройка `.env` и проверка программой

1. Скопируйте блок «Хранилище файлов» из `.env.example` в свой `.env`.
2. Для локальной проверки с реальным облаком:

```env
STORAGE_BACKEND=nextcloud
NEXTCLOUD_URL=https://cloud.example.edu
NEXTCLOUD_PUBLIC_URL=
NEXTCLOUD_USER=plans-app
NEXTCLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
NEXTCLOUD_ROOT=plans
NEXTCLOUD_DOWNLOAD_MODE=direct
NEXTCLOUD_SHARE_TTL_DAYS=7
NEXTCLOUD_VERIFY_TLS=true
```

3. Из каталога `src/education_site`:

```bash
python manage.py check_nextcloud
```

Команда печатает шаги «OK / ошибка / что делать», проверяет capabilities,
круг запись–чтение–переименование–удаление и открытие публичной ссылки,
после себя следов не оставляет.

4. Если режим `direct` недоступен (ссылки запрещены), поставьте
   `NEXTCLOUD_DOWNLOAD_MODE=proxy` — файлы будут отдаваться через программу.

5. Перенос уже загруженных локальных файлов (на сервере, после успешной проверки):

```bash
python manage.py migrate_storage_backend --from local --to nextcloud --verify
```

Затем оставьте `STORAGE_BACKEND=nextcloud` и перезапустите сервисы.
Подробности перехода — в [deployment.md](deployment.md).
