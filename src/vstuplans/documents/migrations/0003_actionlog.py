import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('documents', '0002_document_approved_version'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActionLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Создано')),
                ('action', models.CharField(db_index=True, max_length=64, verbose_name='Действие')),
                ('object_type', models.CharField(blank=True, default='', max_length=64, verbose_name='Тип объекта')),
                ('object_id', models.CharField(blank=True, db_index=True, default='', max_length=64, verbose_name='Идентификатор')),
                ('metadata', models.JSONField(blank=True, default=dict, verbose_name='Детали')),
                (
                    'actor',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='action_logs',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Исполнитель',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Запись аудита',
                'verbose_name_plural': 'Журнал действий',
                'ordering': ('-created_at',),
            },
        ),
    ]
