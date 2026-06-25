# plans/management/commands/update_from_yandex.py
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from documents.upload import ingest_plx_file
from plans.yandex_client import download_plx_file, get_yandex_client, list_plx_files


class Command(BaseCommand):
    help = 'Скачивает все PLX с Яндекс.Диска и загружает через documents upload pipeline'

    def handle(self, *args, **options):
        disk = get_yandex_client()
        if not disk.check_token():
            self.stdout.write(self.style.ERROR('Неверный токен Яндекс.Диска'))
            return

        plx_files = list_plx_files(disk, settings.YANDEX_DISK_BASE_PATH)
        self.stdout.write(f'Найдено PLX-файлов: {len(plx_files)}')

        userfiles_root = Path(settings.USERFILES_ROOT)
        userfiles_root.mkdir(parents=True, exist_ok=True)

        created = 0
        updated = 0
        duplicates = 0
        errors = 0

        for remote_file in plx_files:
            rel_path = str(remote_file.path)
            if rel_path.startswith(settings.YANDEX_DISK_BASE_PATH.rstrip('/')):
                rel_path = rel_path[len(settings.YANDEX_DISK_BASE_PATH.rstrip('/')):].lstrip('/')
            safe_rel_path = rel_path.replace('/', os.sep).replace('\\', '/')

            with tempfile.NamedTemporaryFile(suffix='.plx', delete=False) as tmp_file:
                tmp_path = tmp_file.name
            try:
                download_plx_file(disk, remote_file.path, tmp_path)
                result = ingest_plx_file(
                    file_path=Path(tmp_path),
                    storage_key=safe_rel_path,
                    auto_link_single_match=True,
                )

                if result.status == 'already_exists':
                    duplicates += 1
                    self.stdout.write(f'Дубликат {safe_rel_path}')
                elif result.message == 'Version uploaded':
                    from documents import models as orm

                    version = orm.DocumentVersion.objects.get(pk=result.version_id)
                    if version.version_number == 1:
                        created += 1
                        self.stdout.write(f'Создан {safe_rel_path}')
                    else:
                        updated += 1
                        self.stdout.write(f'Новая версия {safe_rel_path}')
                else:
                    updated += 1
                    self.stdout.write(f'Обработан {safe_rel_path}')

            except Exception as e:
                self.stderr.write(f'Ошибка обработки {remote_file.name}: {e}')
                errors += 1
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        self.stdout.write(
            self.style.SUCCESS(
                f'\nГотово: создано {created}, версий {updated}, дубликатов {duplicates}, ошибок {errors}'
            )
        )
