from django.db import migrations


def create_role_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in (
        'reader',
        'curriculum_developer',
        'reviewer',
        'manager',
        'administrator',
    ):
        Group.objects.get_or_create(name=name)


def remove_role_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(
        name__in=(
            'reader',
            'curriculum_developer',
            'reviewer',
            'manager',
            'administrator',
        )
    ).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_role_groups, remove_role_groups),
    ]
