import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('documents', '0002_document_approved_version'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeedbackReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created')),
                (
                    'kind',
                    models.CharField(
                        choices=[('problem', 'Problem'), ('question', 'Question'), ('suggestion', 'Suggestion')],
                        max_length=32,
                        verbose_name='Kind',
                    ),
                ),
                ('subject', models.CharField(max_length=255, verbose_name='Subject')),
                ('body', models.TextField(verbose_name='Message')),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('new', 'New'),
                            ('in_progress', 'In progress'),
                            ('resolved', 'Resolved'),
                            ('rejected', 'Rejected'),
                        ],
                        db_index=True,
                        default='new',
                        max_length=32,
                        verbose_name='Status',
                    ),
                ),
                ('staff_reply', models.TextField(blank=True, default='', verbose_name='Staff reply')),
                ('handled_at', models.DateTimeField(blank=True, null=True, verbose_name='Handled at')),
                ('context', models.JSONField(blank=True, default=dict, verbose_name='Context')),
                (
                    'author',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='feedback_reports',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Author',
                    ),
                ),
                (
                    'document',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='feedback_reports',
                        to='documents.document',
                        verbose_name='Document',
                    ),
                ),
                (
                    'handled_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='handled_feedback_reports',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Handled by',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Feedback report',
                'verbose_name_plural': 'Feedback reports',
                'ordering': ('-created_at',),
            },
        ),
    ]
