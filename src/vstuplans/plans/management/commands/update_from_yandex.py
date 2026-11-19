from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Устарело: используйте sync_external_storage'

    def handle(self, *args, **options):
        self.stderr.write(
            self.style.WARNING(
                'Команда update_from_yandex устарела. '
                'Используйте: python manage.py sync_external_storage --connection=uo_readonly'
            )
        )
