from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from external_sync.models import ExternalConnection, SyncRun, SyncRunStatus
from external_sync.services.queue_mode import parse_queue_mode
from external_sync.services.reconcile import ReconciliationService


class Command(BaseCommand):
    help = 'Обрабатывает очередь SyncRun и периодически запускает подключения по расписанию'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Один цикл (очередь + при необходимости расписание), без бесконечного ожидания',
        )
        parser.add_argument(
            '--poll-seconds',
            type=int,
            default=int(getattr(settings, 'SYNC_WORKER_POLL_SECONDS', 30)),
            help='Пауза между циклами в режиме демона',
        )

    def handle(self, *args, **options):
        once = options['once']
        poll = max(5, int(options['poll_seconds']))

        while True:
            processed = self._process_queue() or self._process_scheduled()
            if once:
                return
            if not processed:
                time.sleep(poll)

    def _process_queue(self) -> bool:
        with transaction.atomic():
            sync_run = (
                SyncRun.objects.select_for_update(skip_locked=True)
                .filter(status=SyncRunStatus.QUEUED)
                .select_related('connection')
                .order_by('created_at')
                .first()
            )
            if sync_run is None:
                return False
            connection = sync_run.connection
            mode = parse_queue_mode(sync_run.idempotency_key)

        self.stdout.write(f'Очередь: прогон {sync_run.id} ({connection.slug}, режим {mode})')
        service = ReconciliationService(connection)
        service.run(
            sync_run=sync_run,
            pull_only=mode == 'pull',
            push_only=mode == 'push',
        )
        return True

    def _process_scheduled(self) -> bool:
        interval = int(getattr(settings, 'SYNC_SCHEDULE_INTERVAL_SECONDS', 3600))
        now = timezone.now()
        ran = False

        for connection in ExternalConnection.objects.filter(enabled=True, schedule_enabled=True):
            last = (
                SyncRun.objects.filter(connection=connection)
                .exclude(status=SyncRunStatus.QUEUED)
                .order_by('-finished_at', '-created_at')
                .first()
            )
            anchor = last.finished_at or last.created_at if last else None
            if anchor and (now - anchor).total_seconds() < interval:
                continue
            if SyncRun.objects.filter(connection=connection, status=SyncRunStatus.QUEUED).exists():
                continue
            active = (
                connection.lease_until and connection.lease_until > now and connection.lease_token
            )
            if active:
                continue

            self.stdout.write(f'Расписание: {connection.slug}')
            ReconciliationService(connection).run(from_schedule=True)
            ran = True

        return ran
