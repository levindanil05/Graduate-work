"""Перенос файлов редакций между реализациями StoragePort (local ↔ nextcloud)."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from documents.infra.hashing import HashingService
from documents.infra.storage import LocalStoragePort
from documents.models import DocumentVersion


class Command(BaseCommand):
    help = 'Копирует файлы редакций из одного хранилища в другое по тем же storage_key'

    def add_arguments(self, parser):
        parser.add_argument('--from', dest='source', required=True, choices=['local', 'nextcloud'])
        parser.add_argument('--to', dest='destination', required=True, choices=['local', 'nextcloud'])
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--verify', action='store_true', help='Сверить размер и хэш после копирования')
        parser.add_argument(
            '--delete-source',
            action='store_true',
            help='Удалить исходный файл только после успешной проверки',
        )

    def handle(self, *args, **options):
        source_name = options['source']
        dest_name = options['destination']
        if source_name == dest_name:
            raise CommandError('--from и --to должны различаться')

        if options['delete_source'] and not options['verify']:
            raise CommandError('--delete-source требует --verify')

        source = self._build(source_name)
        destination = self._build(dest_name)
        hashing = HashingService()

        migrated = 0
        skipped = 0
        missing = 0
        errors = 0

        qs = DocumentVersion.objects.exclude(storage_key='').exclude(storage_key__isnull=True)
        for version in qs.iterator():
            key = version.storage_key
            label = f'{key} (редакция {version.id})'
            try:
                if not source.exists(key):
                    missing += 1
                    self.stderr.write(f'Нет в источнике: {label}')
                    continue
                if destination.exists(key):
                    skipped += 1
                    continue
                if options['dry_run']:
                    self.stdout.write(f'[dry-run] перенести {label}')
                    migrated += 1
                    continue
                with source.local_copy(key) as local_path:
                    destination.save(local_path, key)
                    if options['verify']:
                        expected_hash = hashing.hash_file(local_path)
                        expected_size = local_path.stat().st_size
                        with destination.local_copy(key) as copied:
                            actual_hash = hashing.hash_file(copied)
                            actual_size = copied.stat().st_size
                        if actual_hash != expected_hash or actual_size != expected_size:
                            raise CommandError(
                                f'Проверка не прошла для {label}: '
                                f'size {expected_size}/{actual_size}, '
                                f'hash {expected_hash}/{actual_hash}'
                            )
                    if options['delete_source']:
                        source.delete(key)
                migrated += 1
                self.stdout.write(f'OK {label}')
            except Exception as exc:  # noqa: BLE001
                errors += 1
                self.stderr.write(f'Ошибка {label}: {exc}')

        summary = (
            f'Готово: перенесено {migrated}, пропущено {skipped}, '
            f'потеряно {missing}, ошибок {errors}'
        )
        if errors or missing:
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
        if not options['dry_run'] and dest_name == 'nextcloud' and errors == 0:
            self.stdout.write(
                'После переноса задайте STORAGE_BACKEND=nextcloud и перезапустите сервисы.'
            )

    def _build(self, name: str):
        if name == 'local':
            return LocalStoragePort()
        from documents.infra.storage_nextcloud import NextcloudStoragePort

        return NextcloudStoragePort()
