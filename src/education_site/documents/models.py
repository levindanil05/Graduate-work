import uuid

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        abstract = True


class VersionStatus(models.TextChoices):
    NEW = 'new', 'Новый'
    ON_REVIEW = 'on_review', 'На проверке'
    NEEDS_FIX = 'needs_fix', 'Требует доработки'
    APPROVED = 'approved', 'Утверждён'
    ARCHIVED = 'archived', 'В архиве'
    INVALID = 'invalid', 'Невалидный'
    TRASHED = 'trashed', 'В корзине'


class DocumentType(models.TextChoices):
    PLX = 'plx', 'Учебный план (PLX)'
    GENERIC = 'generic', 'Общий документ'


class Document(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_type = models.CharField(
        max_length=80,
        choices=DocumentType.choices,
        db_index=True,
        verbose_name='Тип',
    )
    canonical_name = models.CharField(max_length=255, db_index=True, verbose_name='Каноническое имя')
    explanation = models.TextField(blank=True, default='', verbose_name='Пояснение')
    extra_data = models.JSONField(default=dict, blank=True, verbose_name='Доп. данные')
    current_version = models.ForeignKey(
        'DocumentVersion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name='Текущая версия',
    )
    approved_version = models.ForeignKey(
        'DocumentVersion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name='Утверждённая версия',
    )

    class Meta:
        verbose_name = 'Документ'
        verbose_name_plural = 'Документы'

    def __str__(self) -> str:
        return self.canonical_name


class DocumentAlias(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=255, db_index=True, unique=True, verbose_name='Алиас')
    alias_source = models.CharField(max_length=64, blank=True, default='', verbose_name='Источник алиаса')

    class Meta:
        verbose_name = 'Алиас документа'
        verbose_name_plural = 'Алиасы документов'

    def __str__(self) -> str:
        return self.alias


class DocumentVersion(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    status = models.CharField(
        max_length=32,
        choices=VersionStatus.choices,
        default=VersionStatus.NEW,
        db_index=True,
        verbose_name='Статус',
    )
    version_number = models.PositiveIntegerField(verbose_name='Номер версии')
    source_filename = models.CharField(max_length=255, verbose_name='Имя файла')
    storage_key = models.CharField(max_length=500, verbose_name='Ключ хранения')
    content_hash = models.CharField(max_length=128, db_index=True, verbose_name='Хэш содержимого')
    created_by_user_id = models.IntegerField(null=True, blank=True, verbose_name='Автор')
    change_comment = models.TextField(blank=True, default='', verbose_name='Комментарий к версии')
    extracted_metadata = models.JSONField(default=dict, blank=True, verbose_name='Метаданные')
    error_messages = models.JSONField(default=list, blank=True, verbose_name='Ошибки')

    class Meta:
        verbose_name = 'Версия документа'
        verbose_name_plural = 'Версии документов'
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'version_number'],
                name='uniq_document_version_number',
            )
        ]

    def __str__(self) -> str:
        return f'{self.document.canonical_name} v{self.version_number}'

    def meta_get(self, key: str, default=''):
        return self.extracted_metadata.get(key, default) if self.extracted_metadata else default

    @property
    def direction_code(self) -> str:
        return self.meta_get('direction_code')

    @property
    def direction(self) -> str:
        return self.meta_get('direction')

    @property
    def faculty(self) -> str:
        # В UI — русская аббр., иначе полное имя (не латиница).
        return self.meta_get('faculty_abbr_ru') or self.meta_get('faculty')

    @property
    def department(self) -> str:
        return self.meta_get('department_abbr_ru') or self.meta_get('department')

    @property
    def faculty_full(self) -> str:
        return self.meta_get('faculty')

    @property
    def department_full(self) -> str:
        return self.meta_get('department')

    @property
    def year_start(self):
        return self.extracted_metadata.get('year_start') if self.extracted_metadata else None

    @property
    def qualification(self) -> str:
        return self.meta_get('qualification')

    @property
    def profile(self) -> str:
        return self.meta_get('profile')

    @property
    def profiles(self) -> list:
        if not self.extracted_metadata:
            return []
        return list(self.extracted_metadata.get('profiles') or [])


class DiscussionThread(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_version = models.OneToOneField(
        DocumentVersion,
        on_delete=models.CASCADE,
        related_name='discussion_thread',
        verbose_name='Версия',
    )

    class Meta:
        verbose_name = 'Обсуждение'
        verbose_name_plural = 'Обсуждения'


class DiscussionMessage(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        DiscussionThread,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Тред',
    )
    author_id = models.IntegerField(null=True, blank=True, verbose_name='Автор')
    after_message_id = models.UUIDField(null=True, blank=True)
    replies_to_message_id = models.UUIDField(null=True, blank=True)
    message = models.TextField(verbose_name='Сообщение')

    class Meta:
        verbose_name = 'Сообщение обсуждения'
        verbose_name_plural = 'Сообщения обсуждения'


class WorkflowTransition(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.CASCADE,
        related_name='workflow_transitions',
        verbose_name='Версия',
    )
    from_status = models.CharField(max_length=32, verbose_name='Из статуса')
    to_status = models.CharField(max_length=32, verbose_name='В статус')
    action = models.CharField(max_length=64, verbose_name='Действие')
    action_comment = models.TextField(blank=True, default='', verbose_name='Комментарий')
    actor_id = models.IntegerField(null=True, blank=True, verbose_name='Исполнитель')

    class Meta:
        verbose_name = 'Переход workflow'
        verbose_name_plural = 'Переходы workflow'


class DocumentTypeStrategy(models.Model):
    document_type = models.CharField(max_length=80, unique=True, verbose_name='Тип документа')
    naming_strategy_key = models.CharField(max_length=120, verbose_name='Стратегия именования')
    rename_policy_key = models.CharField(max_length=120, blank=True, default='')
    metadata_extractor_key = models.CharField(max_length=120, blank=True, default='')

    class Meta:
        verbose_name = 'Стратегия типа документа'
        verbose_name_plural = 'Стратегии типов документов'
