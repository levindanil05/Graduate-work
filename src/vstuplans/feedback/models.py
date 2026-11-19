from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class FeedbackKind(models.TextChoices):
    PROBLEM = 'problem', 'Сообщение о проблеме'
    QUESTION = 'question', 'Вопрос'
    SUGGESTION = 'suggestion', 'Предложение'


class FeedbackStatus(models.TextChoices):
    NEW = 'new', 'Новое'
    IN_PROGRESS = 'in_progress', 'В работе'
    RESOLVED = 'resolved', 'Решено'
    REJECTED = 'rejected', 'Отклонено'


class FeedbackReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedback_reports',
        verbose_name=_('Author'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created'))
    kind = models.CharField(max_length=32, choices=FeedbackKind.choices, verbose_name=_('Kind'))
    subject = models.CharField(max_length=255, verbose_name=_('Subject'))
    body = models.TextField(verbose_name=_('Message'))
    status = models.CharField(
        max_length=32,
        choices=FeedbackStatus.choices,
        default=FeedbackStatus.NEW,
        db_index=True,
        verbose_name=_('Status'),
    )
    staff_reply = models.TextField(blank=True, default='', verbose_name=_('Staff reply'))
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='handled_feedback_reports',
        verbose_name=_('Handled by'),
    )
    handled_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Handled at'))
    context = models.JSONField(default=dict, blank=True, verbose_name=_('Context'))
    document = models.ForeignKey(
        'documents.Document',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='feedback_reports',
        verbose_name=_('Document'),
    )

    class Meta:
        verbose_name = _('Feedback report')
        verbose_name_plural = _('Feedback reports')
        ordering = ('-created_at',)

    def __str__(self) -> str:
        return f'{self.subject} ({self.get_kind_display()})'
