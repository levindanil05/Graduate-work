from __future__ import annotations

import uuid

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        abstract = True


class WriteMode(models.TextChoices):
    READ_ONLY = 'read_only', 'Только чтение'
    READ_WRITE = 'read_write', 'Чтение и запись'


class OnActiveMissing(models.TextChoices):
    ARCHIVE_LOCAL = 'archive_local', 'Архивировать локально'
    KEEP_AND_REPORT = 'keep_and_report', 'Сохранить и сообщить'


class RemoteRole(models.TextChoices):
    ACTIVE = 'active', 'Актуальная'
    ARCHIVE = 'archive', 'Архивная'
    IGNORED = 'ignored', 'Игнорируется'


class ReplicaSyncState(models.TextChoices):
    IN_SYNC = 'in_sync', 'Синхронизирована'
    PENDING_PUSH = 'pending_push', 'Ожидает отправки'
    PAUSED_BY_SWITCH = 'paused_by_switch', 'Приостановлено настройкой'
    CONFLICT = 'conflict', 'Расхождение'
    MISSING_REMOTE = 'missing_remote', 'Нет на диске'
    STALE = 'stale', 'Устарела'


class SyncRunStatus(models.TextChoices):
    QUEUED = 'queued', 'В очереди'
    PLANNING = 'planning', 'Планирование'
    APPLYING = 'applying', 'Применение'
    COMPLETED = 'completed', 'Завершён'
    PAUSED = 'paused', 'Приостановлен'
    FAILED = 'failed', 'Ошибка'


class OutboundKind(models.TextChoices):
    PUBLISH_ACTIVE = 'publish_active', 'Опубликовать актуальную'
    MOVE_TO_ARCHIVE = 'move_to_archive', 'Переместить в архив'
    NOOP = 'noop', 'Без действия'


class OutboundStatus(models.TextChoices):
    PENDING = 'pending', 'Ожидает'
    PAUSED_BY_SWITCH = 'paused_by_switch', 'Приостановлено настройкой'
    IN_PROGRESS = 'in_progress', 'Выполняется'
    DONE = 'done', 'Выполнено'
    FAILED = 'failed', 'Ошибка'


class ExternalSyncSettings(models.Model):
    external_sync_enabled = models.BooleanField(
        default=False,
        verbose_name='Внешняя синхронизация',
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Настройки внешней синхронизации'
        verbose_name_plural = 'Настройки внешней синхронизации'

    def __str__(self) -> str:
        state = 'включена' if self.external_sync_enabled else 'выключена'
        return f'Внешняя синхронизация ({state})'

    @classmethod
    def get_solo(cls) -> ExternalSyncSettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ExternalConnection(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=64, unique=True, verbose_name='Код')
    name = models.CharField(max_length=255, verbose_name='Название')
    provider_key = models.CharField(max_length=64, default='yandex_disk', verbose_name='Провайдер')
    root_path = models.CharField(max_length=500, default='/', verbose_name='Корневой путь')
    credential_ref = models.CharField(max_length=128, verbose_name='Ссылка на секрет')
    write_mode = models.CharField(
        max_length=16,
        choices=WriteMode.choices,
        default=WriteMode.READ_WRITE,
        verbose_name='Режим доступа',
    )
    enabled = models.BooleanField(default=True, verbose_name='Подключение включено')
    pull_enabled = models.BooleanField(default=False, verbose_name='Получать изменения')
    push_enabled = models.BooleanField(default=False, verbose_name='Отправлять утверждённые версии')
    schedule_enabled = models.BooleanField(default=False, verbose_name='Запускать по расписанию')
    manual_run_enabled = models.BooleanField(default=True, verbose_name='Разрешить ручной запуск')
    on_active_missing = models.CharField(
        max_length=32,
        choices=OnActiveMissing.choices,
        default=OnActiveMissing.ARCHIVE_LOCAL,
        verbose_name='Если актуальный файл исчез на диске',
    )
    last_checkpoint_at = models.DateTimeField(null=True, blank=True, verbose_name='Последний checkpoint')
    lease_token = models.CharField(max_length=64, blank=True, default='', verbose_name='Lease')
    lease_until = models.DateTimeField(null=True, blank=True, verbose_name='Lease до')

    class Meta:
        verbose_name = 'Внешнее подключение'
        verbose_name_plural = 'Внешние подключения'

    def __str__(self) -> str:
        return self.name

    def is_read_only_mode(self) -> bool:
        return self.write_mode == WriteMode.READ_ONLY

    def save(self, *args, **kwargs):
        if self.write_mode == WriteMode.READ_ONLY:
            self.push_enabled = False
        super().save(*args, **kwargs)
        if self.pull_enabled:
            ExternalConnection.objects.exclude(pk=self.pk).filter(pull_enabled=True).update(
                pull_enabled=False
            )


class RemoteObjectSnapshot(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        ExternalConnection,
        on_delete=models.CASCADE,
        related_name='snapshots',
        verbose_name='Подключение',
    )
    remote_path = models.CharField(max_length=500, verbose_name='Путь на диске')
    remote_id = models.CharField(max_length=128, blank=True, default='', verbose_name='ID ресурса')
    role = models.CharField(max_length=16, choices=RemoteRole.choices, verbose_name='Роль')
    size = models.BigIntegerField(default=0, verbose_name='Размер')
    md5 = models.CharField(max_length=128, blank=True, default='', verbose_name='MD5')
    modified_at = models.DateTimeField(null=True, blank=True, verbose_name='Изменён на диске')
    content_hash = models.CharField(max_length=128, blank=True, default='', verbose_name='Хэш содержимого')
    version = models.ForeignKey(
        'documents.DocumentVersion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='remote_snapshots',
        verbose_name='Версия',
    )

    class Meta:
        verbose_name = 'Слепок удалённого объекта'
        verbose_name_plural = 'Слепки удалённых объектов'
        constraints = [
            models.UniqueConstraint(
                fields=['connection', 'remote_path'],
                name='uniq_snapshot_connection_path',
            )
        ]


class ExternalReplica(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        ExternalConnection,
        on_delete=models.CASCADE,
        related_name='replicas',
        verbose_name='Подключение',
    )
    version = models.ForeignKey(
        'documents.DocumentVersion',
        on_delete=models.CASCADE,
        related_name='external_replicas',
        verbose_name='Версия',
    )
    remote_path = models.CharField(max_length=500, verbose_name='Путь на диске')
    role = models.CharField(max_length=16, choices=RemoteRole.choices, verbose_name='Роль')
    is_primary = models.BooleanField(default=False, verbose_name='Основная копия')
    sync_state = models.CharField(
        max_length=32,
        choices=ReplicaSyncState.choices,
        default=ReplicaSyncState.IN_SYNC,
        verbose_name='Состояние согласования',
    )
    last_reconciled_at = models.DateTimeField(null=True, blank=True, verbose_name='Последнее согласование')

    class Meta:
        verbose_name = 'Внешняя копия'
        verbose_name_plural = 'Внешние копии'
        constraints = [
            models.UniqueConstraint(
                fields=['connection', 'remote_path'],
                name='uniq_replica_connection_path',
            )
        ]


class SyncRun(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        ExternalConnection,
        on_delete=models.CASCADE,
        related_name='sync_runs',
        verbose_name='Подключение',
    )
    status = models.CharField(
        max_length=16,
        choices=SyncRunStatus.choices,
        default=SyncRunStatus.QUEUED,
        verbose_name='Статус',
    )
    idempotency_key = models.CharField(max_length=128, blank=True, default='', verbose_name='Ключ идемпотентности')
    imported_count = models.PositiveIntegerField(default=0, verbose_name='Импортировано')
    published_count = models.PositiveIntegerField(default=0, verbose_name='Опубликовано')
    archived_count = models.PositiveIntegerField(default=0, verbose_name='Архивировано')
    duplicates_count = models.PositiveIntegerField(default=0, verbose_name='Дубликаты')
    conflicts_count = models.PositiveIntegerField(default=0, verbose_name='Конфликты')
    skipped_count = models.PositiveIntegerField(default=0, verbose_name='Пропущено')
    errors_count = models.PositiveIntegerField(default=0, verbose_name='Ошибки')
    report_lines = models.JSONField(default=list, blank=True, verbose_name='Строки отчёта')
    stop_reason = models.TextField(blank=True, default='', verbose_name='Причина остановки')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='Завершён')

    class Meta:
        verbose_name = 'Прогон синхронизации'
        verbose_name_plural = 'Прогоны синхронизации'


class OutboundIntent(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        ExternalConnection,
        on_delete=models.CASCADE,
        related_name='outbound_intents',
        verbose_name='Подключение',
    )
    version = models.ForeignKey(
        'documents.DocumentVersion',
        on_delete=models.CASCADE,
        related_name='outbound_intents',
        verbose_name='Версия',
    )
    kind = models.CharField(max_length=32, choices=OutboundKind.choices, verbose_name='Тип')
    idempotency_key = models.CharField(max_length=128, unique=True, verbose_name='Ключ идемпотентности')
    status = models.CharField(
        max_length=32,
        choices=OutboundStatus.choices,
        default=OutboundStatus.PENDING,
        verbose_name='Статус',
    )
    desired_remote_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Целевой путь')
    error_message = models.TextField(blank=True, default='', verbose_name='Ошибка')

    class Meta:
        verbose_name = 'Исходящее намерение'
        verbose_name_plural = 'Исходящие намерения'


class SyncConflict(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        ExternalConnection,
        on_delete=models.CASCADE,
        related_name='conflicts',
        verbose_name='Подключение',
    )
    version = models.ForeignKey(
        'documents.DocumentVersion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sync_conflicts',
        verbose_name='Версия',
    )
    remote_path = models.CharField(max_length=500, blank=True, default='', verbose_name='Путь на диске')
    summary = models.TextField(verbose_name='Описание')
    resolved = models.BooleanField(default=False, verbose_name='Разрешён')

    class Meta:
        verbose_name = 'Конфликт синхронизации'
        verbose_name_plural = 'Конфликты синхронизации'


class SwitchAuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    setting_name = models.CharField(max_length=128, verbose_name='Настройка')
    connection = models.ForeignKey(
        ExternalConnection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='switch_audits',
        verbose_name='Подключение',
    )
    old_value = models.CharField(max_length=255, blank=True, default='', verbose_name='Было')
    new_value = models.CharField(max_length=255, blank=True, default='', verbose_name='Стало')
    actor_id = models.IntegerField(null=True, blank=True, verbose_name='Исполнитель')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Когда')

    class Meta:
        verbose_name = 'Аудит переключения'
        verbose_name_plural = 'Аудит переключений'
        ordering = ['-created_at']
