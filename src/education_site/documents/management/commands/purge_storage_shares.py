"""Удаление просроченных записей публичных ссылок Nextcloud."""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Удаляет просроченные StorageShareLink и отзывает их в Nextcloud'

    def handle(self, *args, **options):
        from documents.infra.storage import build_storage_port
        from documents.models import StorageShareLink

        now = timezone.now()
        expired = list(StorageShareLink.objects.filter(expires_at__lte=now))
        if not expired:
            self.stdout.write('Просроченных ссылок нет')
            return

        storage = build_storage_port()
        keys = [link.storage_key for link in expired]
        try:
            storage.revoke_direct_urls(keys)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f'Ошибка отзыва ссылок: {exc}')
            # На случай если revoke не удалил записи (локальный порт — no-op)
            StorageShareLink.objects.filter(storage_key__in=keys).delete()

        self.stdout.write(self.style.SUCCESS(f'Удалено ссылок: {len(keys)}'))
