import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from documents.upload import ingest_plx_file


class Command(BaseCommand):
    help = 'Импортирует .plx из userfiles через documents upload pipeline'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            default=str(getattr(settings, 'USERFILES_ROOT', '')),
            help='Корневая папка userfiles (по умолчанию settings.USERFILES_ROOT)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать, что будет импортировано (без записи в БД)',
        )

    def handle(self, *args, **options):
        root = Path(options['path']).resolve()
        dry_run = bool(options['dry_run'])

        if not root.exists() or not root.is_dir():
            self.stderr.write(self.style.ERROR(f'Папка не найдена: {root}'))
            return

        created = 0
        updated = 0
        duplicates = 0
        failed = 0
        scanned = 0

        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if not filename.lower().endswith('.plx'):
                    continue

                scanned += 1
                abs_path = Path(dirpath) / filename
                rel_path = abs_path.relative_to(root).as_posix()

                if dry_run:
                    self.stdout.write(f'[DRY] {rel_path}')
                    continue

                try:
                    result = ingest_plx_file(
                        file_path=abs_path,
                        storage_key=rel_path,
                        auto_link_single_match=True,
                    )
                    if result.status == 'already_exists':
                        duplicates += 1
                    else:
                        from documents import models as orm

                        version = orm.DocumentVersion.objects.get(pk=result.version_id)
                        if version.version_number == 1:
                            created += 1
                        else:
                            updated += 1
                except Exception as exc:
                    failed += 1
                    self.stderr.write(f'{rel_path}: {exc}')

        self.stdout.write(self.style.SUCCESS(f'Сканировано файлов: {scanned}'))
        self.stdout.write(self.style.SUCCESS(f'Создано документов: {created}'))
        self.stdout.write(self.style.SUCCESS(f'Новых версий: {updated}'))
        self.stdout.write(self.style.WARNING(f'Дубликатов: {duplicates}'))
        self.stdout.write(self.style.WARNING(f'Ошибок: {failed}'))
