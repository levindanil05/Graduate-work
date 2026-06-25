from django.core.management.base import BaseCommand

from documents.infra.hashing import HashingService
from documents.infra.storage import UserfilesStoragePort
from documents.upload import migrate_educational_plan_record
from plans.models import EducationalPlan


class Command(BaseCommand):
    help = 'Переносит записи EducationalPlan в модель documents (Document + DocumentVersion)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать количество записей для переноса',
        )

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        plans = EducationalPlan.objects.exclude(source_path='').order_by('id')
        total = plans.count()

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'К переносу: {total} записей'))
            return

        storage = UserfilesStoragePort()
        hasher = HashingService()
        migrated = 0
        skipped = 0

        for plan in plans:
            from documents import models as orm

            if orm.DocumentVersion.objects.filter(storage_key=plan.source_path).exists():
                skipped += 1
                continue
            migrate_educational_plan_record(plan, storage=storage, hasher=hasher)
            migrated += 1

        self.stdout.write(self.style.SUCCESS(f'Перенесено: {migrated}, пропущено: {skipped}, всего в plans: {total}'))
