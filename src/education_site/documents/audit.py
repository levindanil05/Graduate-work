from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models


class ActionLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Создано')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='action_logs',
        verbose_name='Исполнитель',
    )
    action = models.CharField(max_length=64, db_index=True, verbose_name='Действие')
    object_type = models.CharField(max_length=64, blank=True, default='', verbose_name='Тип объекта')
    object_id = models.CharField(max_length=64, blank=True, default='', db_index=True, verbose_name='Идентификатор')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Детали')

    class Meta:
        verbose_name = 'Запись аудита'
        verbose_name_plural = 'Журнал действий'
        ordering = ('-created_at',)

    def __str__(self) -> str:
        return f'{self.action} ({self.created_at:%Y-%m-%d %H:%M})'


def log_action(
    *,
    action: str,
    actor=None,
    object_type: str = '',
    object_id: str = '',
    metadata: dict[str, Any] | None = None,
) -> ActionLog:
    return ActionLog.objects.create(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id else '',
        metadata=metadata or {},
    )
