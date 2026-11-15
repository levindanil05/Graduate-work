"""Пошаговая диагностика подключения к Nextcloud."""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Проверяет доступ к Nextcloud: вход, папка, запись/чтение, публичная ссылка'

    def handle(self, *args, **options):
        self.stdout.write('Параметры (пароль скрыт):')
        self.stdout.write(f'  STORAGE_BACKEND={getattr(settings, "STORAGE_BACKEND", "")}')
        self.stdout.write(f'  NEXTCLOUD_URL={settings.NEXTCLOUD_URL or "(пусто)"}')
        self.stdout.write(
            f'  NEXTCLOUD_PUBLIC_URL={getattr(settings, "NEXTCLOUD_PUBLIC_URL", "") or "(= URL)"}'
        )
        self.stdout.write(f'  NEXTCLOUD_USER={settings.NEXTCLOUD_USER or "(пусто)"}')
        self.stdout.write(
            f'  NEXTCLOUD_APP_PASSWORD={"***" if settings.NEXTCLOUD_APP_PASSWORD else "(пусто)"}'
        )
        self.stdout.write(f'  NEXTCLOUD_ROOT={settings.NEXTCLOUD_ROOT}')
        self.stdout.write(f'  NEXTCLOUD_DOWNLOAD_MODE={settings.NEXTCLOUD_DOWNLOAD_MODE}')
        self.stdout.write(f'  NEXTCLOUD_SHARE_TTL_DAYS={settings.NEXTCLOUD_SHARE_TTL_DAYS}')
        self.stdout.write(f'  NEXTCLOUD_VERIFY_TLS={settings.NEXTCLOUD_VERIFY_TLS!r}')

        missing = [
            name
            for name, value in (
                ('NEXTCLOUD_URL', settings.NEXTCLOUD_URL),
                ('NEXTCLOUD_USER', settings.NEXTCLOUD_USER),
                ('NEXTCLOUD_APP_PASSWORD', settings.NEXTCLOUD_APP_PASSWORD),
            )
            if not value
        ]
        if missing:
            raise CommandError(
                'Не заданы обязательные переменные: '
                + ', '.join(missing)
                + '. См. docs/nextcloud-setup.md'
            )

        from documents.infra.storage_nextcloud import NextcloudError, NextcloudStoragePort

        storage = NextcloudStoragePort()
        failed = False

        self.stdout.write('')
        self.stdout.write('1. Возможности сервера (capabilities)…')
        try:
            caps = storage.fetch_capabilities()
            ocs = (caps.get('ocs') or {}).get('data') or {}
            version = ((ocs.get('version') or {}).get('string')) or '?'
            files_sharing = ((ocs.get('capabilities') or {}).get('files_sharing') or {})
            public = files_sharing.get('public') or {}
            enabled = public.get('enabled', False)
            expire = public.get('expire_date') or {}
            self.stdout.write(self.style.SUCCESS(f'   OK — версия Nextcloud: {version}'))
            self.stdout.write(
                f'   Публичные ссылки: {"включены" if enabled else "ВЫКЛЮЧЕНЫ"}'
            )
            if expire:
                self.stdout.write(
                    f'   Срок ссылок: enforced={expire.get("enforced")}, '
                    f'days={expire.get("days")}, '
                    f'forced={expire.get("forced")}'
                )
            if not enabled:
                self.stdout.write(
                    self.style.WARNING(
                        '   Публичные ссылки выключены — режим direct недоступен. '
                        'Поставьте NEXTCLOUD_DOWNLOAD_MODE=proxy или включите общий доступ.'
                    )
                )
        except NextcloudError as exc:
            failed = True
            self.stdout.write(self.style.ERROR(f'   Ошибка: {exc}'))
            self.stdout.write('   Проверьте URL, логин и пароль приложения (401 → неверный пароль).')

        self.stdout.write('2. Круг запись → чтение → переименование → ссылка → удаление…')
        try:
            result = storage.probe_roundtrip()
            for key in ('save', 'exists', 'read', 'rename', 'delete'):
                ok = result.get(key)
                style = self.style.SUCCESS if ok else self.style.ERROR
                self.stdout.write(style(f'   {key}: {"OK" if ok else "FAIL"}'))
                if not ok:
                    failed = True
            share_ok = result.get('share')
            named_ok = result.get('share_with_filename')
            self.stdout.write(
                (self.style.SUCCESS if share_ok else self.style.WARNING)(
                    f'   share /s/TOKEN/download: {"OK" if share_ok else "FAIL"}'
                )
            )
            self.stdout.write(
                (self.style.SUCCESS if named_ok else self.style.WARNING)(
                    f'   share /s/TOKEN/download/<имя>: {"OK" if named_ok else "FAIL"}'
                )
            )
            if result.get('share_url'):
                self.stdout.write(f'   Пример URL: {result["share_url"]}')
            if not share_ok:
                failed = True
                self.stdout.write(
                    self.style.WARNING(
                        '   Прямая ссылка не открылась. Для работы поставьте '
                        'NEXTCLOUD_DOWNLOAD_MODE=proxy или исправьте настройки общего доступа.'
                    )
                )
            elif not named_ok:
                self.stdout.write(
                    self.style.WARNING(
                        '   Вариант с именем файла не сработал — программа будет использовать '
                        'URL без имени или proxy.'
                    )
                )
        except Exception as exc:  # noqa: BLE001
            failed = True
            self.stdout.write(self.style.ERROR(f'   Ошибка: {exc}'))

        self.stdout.write('')
        if failed:
            raise CommandError(
                'Проверка завершилась с ошибками. См. docs/nextcloud-setup.md'
            )
        mode = settings.NEXTCLOUD_DOWNLOAD_MODE
        self.stdout.write(
            self.style.SUCCESS(
                f'Готово. Можно ставить STORAGE_BACKEND=nextcloud '
                f'(текущий режим скачивания: {mode}).'
            )
        )
