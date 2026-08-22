from django.core.management.base import BaseCommand, CommandError

from external_sync.models import ExternalConnection
from external_sync.services.reconcile import ReconciliationService


class Command(BaseCommand):
    help = 'Согласование с внешним хранилищем для выбранного подключения'

    def add_arguments(self, parser):
        parser.add_argument(
            '--connection',
            required=True,
            help='Код подключения (uo_readonly или mike_rw)',
        )
        parser.add_argument('--pull-only', action='store_true', help='Только получение изменений')
        parser.add_argument('--push-only', action='store_true', help='Только отправка намерений')

    def handle(self, *args, **options):
        slug = options['connection']
        try:
            connection = ExternalConnection.objects.get(slug=slug)
        except ExternalConnection.DoesNotExist as exc:
            raise CommandError(f'Подключение {slug!r} не найдено') from exc

        if options['pull_only'] and options['push_only']:
            raise CommandError('Нельзя одновременно указывать --pull-only и --push-only')

        service = ReconciliationService(connection)
        sync_run = service.run(
            pull_only=options['pull_only'],
            push_only=options['push_only'],
        )

        self.stdout.write(f'Прогон {sync_run.id}: {sync_run.get_status_display()}')
        self.stdout.write(
            f'Импортировано: {sync_run.imported_count}, опубликовано: {sync_run.published_count}, '
            f'дубликаты: {sync_run.duplicates_count}, ошибки: {sync_run.errors_count}'
        )
        if sync_run.stop_reason:
            self.stdout.write(self.style.WARNING(sync_run.stop_reason))
        for line in sync_run.report_lines or []:
            self.stdout.write(line)
