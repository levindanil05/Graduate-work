from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from documents.entities import VersionStatus
from documents.factory import build_document_service
from documents.models import Document


class Command(BaseCommand):
    help = 'Удаляет документы, находящиеся в корзине дольше TRASH_RETENTION_DAYS'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Только показать, что будет удалено')

    def handle(self, *args, **options):
        retention_days = int(getattr(settings, 'TRASH_RETENTION_DAYS', 30))
        cutoff = timezone.now() - timedelta(days=retention_days)
        dry_run = options['dry_run']

        stale_ids = (
            Document.objects.filter(current_version__status=VersionStatus.TRASHED)
            .filter(current_version__updated_at__lt=cutoff)
            .values_list('pk', flat=True)
            .distinct()
        )

        count = 0
        service = build_document_service()
        for document_id in stale_ids:
            if dry_run:
                doc = Document.objects.filter(pk=document_id).select_related('current_version').first()
                name = doc.canonical_name if doc else str(document_id)
                self.stdout.write(f'[dry-run] {document_id} ({name})')
                count += 1
                continue
            try:
                service.hard_delete_document(document_id=document_id, actor_user_id=0)
                count += 1
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f'Ошибка {document_id}: {exc}')

        if count:
            self.stdout.write(
                self.style.SUCCESS(
                    f'{"Найдено" if dry_run else "Удалено"} документов: {count} (порог {retention_days} дн.)'
                )
            )
        else:
            self.stdout.write('Нет документов для удаления.')
