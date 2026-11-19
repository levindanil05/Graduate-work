from django.db import migrations


def seed_connections(apps, schema_editor):
    ExternalConnection = apps.get_model('external_sync', 'ExternalConnection')
    ExternalSyncSettings = apps.get_model('external_sync', 'ExternalSyncSettings')

    ExternalSyncSettings.objects.get_or_create(
        pk=1,
        defaults={'external_sync_enabled': False},
    )

    ExternalConnection.objects.update_or_create(
        slug='uo_readonly',
        defaults={
            'name': 'Яндекс.Диск УО (только просмотр)',
            'provider_key': 'yandex_disk',
            'root_path': '/',
            'credential_ref': 'YANDEX_DISK_UO_READONLY_TOKEN',
            'write_mode': 'read_only',
            'enabled': True,
            'pull_enabled': False,
            'push_enabled': False,
            'manual_run_enabled': True,
        },
    )
    ExternalConnection.objects.update_or_create(
        slug='mike_rw',
        defaults={
            'name': 'Яндекс.Диск — копия Mike',
            'provider_key': 'yandex_disk',
            'root_path': '/',
            'credential_ref': 'YANDEX_DISK_MIKE_RW_TOKEN',
            'write_mode': 'read_write',
            'enabled': True,
            'pull_enabled': False,
            'push_enabled': False,
            'manual_run_enabled': True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('external_sync', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_connections, migrations.RunPython.noop),
    ]
