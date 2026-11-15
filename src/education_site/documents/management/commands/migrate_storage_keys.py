from __future__ import annotations

from django.core.management.base import BaseCommand

from documents.infra.storage import UserfilesStoragePort, build_storage_port
from documents.models import DocumentVersion


class Command(BaseCommand):
    help = 'Копирует файлы редакций в неизменяемые ключи documents/{doc_id}/{version_id}.plx'

    def handle(self, *args, **options):
        storage = build_storage_port()
        migrated = 0
        skipped = 0

        for version in DocumentVersion.objects.select_related('document').iterator():
            target_key = UserfilesStoragePort.version_storage_key(version.document_id, version.id)
            if version.storage_key == target_key:
                skipped += 1
                continue
            if not storage.exists(version.storage_key):
                self.stderr.write(f'Файл не найден: {version.storage_key} (v{version.id})')
                continue
            if storage.exists(target_key):
                skipped += 1
                continue
            with storage.local_copy(version.storage_key) as source:
                storage.save(source, target_key)
            version.storage_key = target_key
            version.save(update_fields=['storage_key', 'updated_at'])
            migrated += 1

        self.stdout.write(
            self.style.SUCCESS(f'Готово: перенесено {migrated}, пропущено {skipped}')
        )
