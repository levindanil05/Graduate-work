from __future__ import annotations

import shutil

from django.core.management.base import BaseCommand

from documents.infra.storage import UserfilesStoragePort
from documents.models import DocumentVersion


class Command(BaseCommand):
    help = 'Копирует файлы версий в неизменяемые ключи documents/{doc_id}/{version_id}.plx'

    def handle(self, *args, **options):
        storage = UserfilesStoragePort()
        migrated = 0
        skipped = 0

        for version in DocumentVersion.objects.select_related('document').iterator():
            target_key = UserfilesStoragePort.version_storage_key(version.document_id, version.id)
            if version.storage_key == target_key:
                skipped += 1
                continue
            source = storage.resolve_path(version.storage_key)
            if not source.exists():
                self.stderr.write(f'Файл не найден: {version.storage_key} (v{version.id})')
                continue
            dest = storage.resolve_path(target_key)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                skipped += 1
                continue
            shutil.copy2(source, dest)
            version.storage_key = target_key
            version.save(update_fields=['storage_key', 'updated_at'])
            migrated += 1

        self.stdout.write(
            self.style.SUCCESS(f'Готово: перенесено {migrated}, пропущено {skipped}')
        )
