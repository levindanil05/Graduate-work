from django.core.management.base import BaseCommand, CommandError

from external_sync.models import ExternalConnection
from external_sync.services.diagnostics import VERDICT_LABELS, run_connection_diagnostics


class Command(BaseCommand):
    help = 'Короткая диагностика внешнего подключения (токен, путь, содержимое верхнего уровня)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--connection',
            required=True,
            help='Код подключения (uo_readonly или mike_rw)',
        )
        parser.add_argument(
            '--list-limit',
            type=int,
            default=30,
            help='Сколько элементов верхнего уровня показать (по умолчанию 30)',
        )

    def handle(self, *args, **options):
        slug = options['connection']
        try:
            connection = ExternalConnection.objects.get(slug=slug)
        except ExternalConnection.DoesNotExist as exc:
            raise CommandError(f'Подключение {slug!r} не найдено') from exc

        report = run_connection_diagnostics(connection, list_limit=options['list_limit'])
        self.stdout.write(
            f'{report.connection_name} ({report.connection_slug}): '
            f'{VERDICT_LABELS.get(report.verdict, report.verdict)}'
        )
        for step in report.steps:
            status_map = {
                'ok': 'OK',
                'fail': 'ОШИБКА',
                'skip': 'пропуск',
                'warn': 'внимание',
            }
            mark = status_map.get(step.status, step.status)
            timing = f' [{step.duration_ms} мс]' if step.duration_ms else ''
            self.stdout.write(f'  [{mark}] {step.title}{timing}')
            self.stdout.write(f'      {step.detail}')

        if report.verdict == 'failed':
            raise CommandError('Диагностика завершилась с ошибками')
