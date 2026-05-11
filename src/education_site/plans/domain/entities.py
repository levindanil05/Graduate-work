from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class DocumentStatus(StrEnum):
    """
    Статус или фаза жизненного цикла документа.
    Краткое имя, как сейчас, а также локализованное имя и описание для подсказки в UI """
    NEW = "new"  # вновь добавленный новый файл (из этого статуса можно сразу удалить без корзины, на случай ошибочной загрузки не того файла, чтобы не засорять корзину и историю версий).
    ON_REVIEW = "on_review"  # документ готов и отправлен на проверку.
    NEEDS_FIX = "needs_fix"  # документ не прошёл проверку и требует доработки.
    APPROVED = "approved"  # документ прошёл проверку и утверждён.
    ARCHIVED = "archived"  # документ архивирован, т.е. не является актуальным и больше не используется.
    INVALID = "invalid"  # документ ошибочен, т.е. файл версии сохранён, но содержимое непригодно или не планируется к исправлению.
    TRASHED = "trashed"  # документ помещён в корзину, т.е. больше не используется и будет физически удалён по истечении срока хранения.


class DocumentType(StrEnum):
    """
    Тип документа.
    Краткое имя, как сейчас, а также локализованное имя и описание, набор расширений  файла, поддерживаемых для этого типа; стратегия разрешения имён для получения привязок к существующим документам.
    """
    STUDY_PLAN = "study_plan" # Вместо этого называть как plx
    # Other types can be added without changing core flows.
    GENERIC = "generic"


@dataclass(slots=True, frozen=True)
class DocumentIdentity:
    """Canonical identity and known aliases for filename matching."""

    canonical_name: str
    aliases: tuple[str, ...] = ()


# @dataclass(slots=True) # Класс должен быть наследуемым, поэтому не надо ограничивать поля.
class Document:
    """Root aggregate for abstract document behavior.

    Может иметь несколько версий, каждая из которых может находиться в своём статусе.
    Типичный пример: актуальная версия утверждена ранее, недавно присланная новая ожидает проверки, а архивные версии давно в архиве.
    Актуальная версия всегда только одна, хотя утверждённых версий может быть несколько. Новая версия становится актуальной только после утверждения (остальные утвержденные версии фактически либо архивные, либо ещё не принятые в актуальную версию, хотя обычно версия должна становиться актуальной сразу после утверждения, вытесняя предыдущую актуальную версию).
    """

    id: UUID = field(default_factory=uuid4)
    document_type: DocumentType = DocumentType.GENERIC
    identity: DocumentIdentity = field(default_factory=lambda: DocumentIdentity(canonical_name=""))
    # status: DocumentStatus = DocumentStatus.NEW  # статус документа должен браться из его актуальной версии.
    description: str = ""  # Always shown with current version in UI.
    extra_data: dict[str, Any] = field(default_factory=dict)
    current_version_id: UUID | None = None  # Текущая, она же актуальная версия документа.
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# @dataclass(slots=True)
class DocumentVersion:
    """Document version descriptor (binary storage handled elsewhere)."""

    id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)  # версией какого документа является.
    status: DocumentStatus = DocumentStatus.NEW
    version_number: int = 1
    source_filename: str = ""
    storage_key: str = ""  # или ID класса, который описывает хранение, собственно, связанного файла в хранилище.
    content_hash: str = ""  # xxhash is preferred for upload deduplication.
    created_by_user_id: int | None = None
    comment_on_changes: str = ""  # Комментарий к изменениям в этой версии (аналог коммит-сообщения в Git).
    extracted_metadata: dict[str, Any] = field(default_factory=dict) # Извлечённые метаданные из файла произвольного вида.
    error_messages: str = ""  # сообщения о внутренних ошибках, которые возникли при обработке файла (например, при извлечении метаданных). Должны дать пользователю намёк на то, что сделать, чтобы исправить проблемы с этим файлом.
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# @dataclass(slots=True)
class WorkflowTransition:
    """Смена статуса версии некоторого документа. Логгируется аналогично транзакции."""
    id: UUID = field(default_factory=uuid4)
    document_version_id: UUID = field(default_factory=uuid4)
    from_status: DocumentStatus = DocumentStatus.NEW
    to_status: DocumentStatus = DocumentStatus.NEW
    action: str = ""  ## TODO : тут не понял назначение поля.
    action_comment: str = ""  # причина перехода (комментарий к переходу).
    actor_user_id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)


# @dataclass(slots=True)
class DiscussionChat:
    """Chat for discussion of a document version (or potentially other subject)."""
    id: UUID = field(default_factory=uuid4)
    subject_type: object = 'DocumentVersion'  # TODO: introduce enum for this.
    subject_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class DiscussionMessage:
    """Version-level discussion message (not to be mixed with explanation).

    Is bound to a specific chat that relates to a document version or potentially other subject.
    """

    id: UUID = field(default_factory=uuid4)
    chat_id: UUID = field(default_factory=uuid4)
    author_user_id: int | None = None
    after_message_id: UUID | None = None
    replies_to_message_id: UUID | None = None
    message: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(slots=True, frozen=True)
class NameMatchResult:
    matched_document_id: UUID | None
    confidence: float
    matched_alias: str | None = None
    closest_document_ids: list[UUID] | None

