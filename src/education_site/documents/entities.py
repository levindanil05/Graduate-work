from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class DocumentType(StrEnum):
    """Document kind. New kinds are added without changing core contracts."""

    PLX = "plx"
    GENERIC = "generic"


class VersionStatus(StrEnum):
    """Lifecycle status is tracked per version, not per document root."""

    NEW = "new"
    ON_REVIEW = "on_review"
    NEEDS_FIX = "needs_fix"
    APPROVED = "approved"
    ARCHIVED = "archived"
    INVALID = "invalid"
    TRASHED = "trashed"


class WorkflowAction(StrEnum):
    """Business action that caused status transition.

    Why this field exists:
    - `from_status`/`to_status` show state change result.
    - `action` stores *intent* (submit, approve, trash, etc.) used in audit/UI analytics.
    """

    SUBMIT = "submit"
    REQUEST_FIX = "request_fix"
    RESUBMIT = "resubmit"
    APPROVE = "approve"
    ARCHIVE = "archive"
    MARK_INVALID = "mark_invalid"
    MOVE_TO_TRASH = "move_to_trash"
    RESTORE = "restore"
    HARD_DELETE = "hard_delete"


@dataclass(frozen=True)
class DocumentIdentity:
    canonical_name: str
    aliases: tuple[str, ...] = ()


@dataclass
class Document:
    """Abstract document root.

    Notes:
    - Root stores identity, explanation and pointers.
    - Current lifecycle status is derived from the current version.
    """

    id: UUID = field(default_factory=uuid4)
    document_type: DocumentType = DocumentType.GENERIC
    identity: DocumentIdentity = field(default_factory=lambda: DocumentIdentity(canonical_name=""))
    # Global explanation is always shown with current version.
    explanation: str = ""
    # Low-frequency fields that do not need dedicated indexed columns.
    extra_data: dict[str, Any] = field(default_factory=dict)
    current_version_id: UUID | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class DocumentVersion:
    """Version descriptor for immutable binary content."""

    id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)
    status: VersionStatus = VersionStatus.NEW
    version_number: int = 1
    source_filename: str = ""
    storage_key: str = ""
    content_hash: str = ""  # xxhash preferred.
    created_by_user_id: int | None = None
    # Comment about what was changed in this version.
    change_comment: str = ""
    extracted_metadata: dict[str, Any] = field(default_factory=dict)
    # User-facing processing/validation errors.
    error_messages: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class WorkflowTransition:
    """Audit record for version status transition."""

    id: UUID = field(default_factory=uuid4)
    document_version_id: UUID = field(default_factory=uuid4)
    from_status: VersionStatus = VersionStatus.NEW
    to_status: VersionStatus = VersionStatus.NEW
    action: WorkflowAction = WorkflowAction.SUBMIT
    # Human explanation of why transition was performed.
    action_comment: str = ""
    actor_user_id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class DiscussionThread:
    """Thread belongs to a specific version."""

    id: UUID = field(default_factory=uuid4)
    document_version_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class DiscussionMessage:
    id: UUID = field(default_factory=uuid4)
    thread_id: UUID = field(default_factory=uuid4)
    author_user_id: int | None = None
    after_message_id: UUID | None = None
    replies_to_message_id: UUID | None = None
    message: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class NameMatchResult:
    matched_document_id: UUID | None
    confidence: float
    matched_alias: str | None = None
    closest_document_ids: tuple[UUID, ...] = ()

