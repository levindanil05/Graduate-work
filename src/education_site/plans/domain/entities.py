from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class DocumentStatus(StrEnum):
    NEW = "new"
    ON_REVIEW = "on_review"
    NEEDS_FIX = "needs_fix"
    APPROVED = "approved"
    ARCHIVED = "archived"
    INVALID = "invalid"
    TRASHED = "trashed"


class DocumentType(StrEnum):
    STUDY_PLAN = "study_plan"
    # Other types can be added without changing core flows.
    GENERIC = "generic"


@dataclass(slots=True, frozen=True)
class DocumentIdentity:
    """Canonical identity and known aliases for filename matching."""

    canonical_name: str
    aliases: tuple[str, ...] = ()


@dataclass(slots=True)
class Document:
    """Root aggregate for abstract document behavior."""

    id: UUID = field(default_factory=uuid4)
    document_type: DocumentType = DocumentType.GENERIC
    identity: DocumentIdentity = field(default_factory=lambda: DocumentIdentity(canonical_name=""))
    status: DocumentStatus = DocumentStatus.NEW
    explanation: str = ""  # Always shown with current version in UI.
    extra_data: dict[str, Any] = field(default_factory=dict)
    current_version_id: UUID | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class DocumentVersion:
    """Immutable version descriptor (binary storage handled elsewhere)."""

    id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)
    version_number: int = 1
    source_filename: str = ""
    storage_key: str = ""
    content_hash: str = ""  # xxhash is preferred for upload deduplication.
    created_by_user_id: int | None = None
    change_comment: str = ""  # Comment about what was changed in this version.
    extracted_metadata: dict[str, Any] = field(default_factory=dict)
    parse_error: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class WorkflowTransition:
    id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)
    from_status: DocumentStatus = DocumentStatus.NEW
    to_status: DocumentStatus = DocumentStatus.NEW
    action: str = ""
    action_comment: str = ""
    actor_user_id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class DiscussionMessage:
    """Version-level discussion message (not to be mixed with explanation)."""

    id: UUID = field(default_factory=uuid4)
    document_version_id: UUID = field(default_factory=uuid4)
    author_user_id: int | None = None
    message: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True, frozen=True)
class NameMatchResult:
    matched_document_id: UUID | None
    confidence: float
    matched_alias: str | None = None

