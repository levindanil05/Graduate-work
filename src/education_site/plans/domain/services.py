from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from .contracts import (
    DiscussionRepository,
    DocumentRepository,
    HashingService,
    MetadataExtractor,
    NameAliasStrategy,
    PermissionService,
    StoragePort,
    VersionRepository,
    WorkflowRepository,
)
from .entities import DiscussionMessage, Document, DocumentStatus, DocumentType, DocumentVersion


@dataclass(slots=True)
class UploadRequest:
    user_id: int
    document_type: DocumentType
    file_path: Path
    source_filename: str
    change_comment: str = ""


@dataclass(slots=True)
class UploadResult:
    document_id: UUID
    version_id: UUID | None
    status: str
    message: str


class DocumentApplicationService:
    """Contract-level service skeleton. Implementation is intentionally omitted."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        versions: VersionRepository,
        workflow: WorkflowRepository,
        discussions: DiscussionRepository,
        storage: StoragePort,
        hashing: HashingService,
        metadata_extractors: list[MetadataExtractor],
        alias_strategies: list[NameAliasStrategy],
        permissions: PermissionService,
    ) -> None:
        self.documents = documents
        self.versions = versions
        self.workflow = workflow
        self.discussions = discussions
        self.storage = storage
        self.hashing = hashing
        self.metadata_extractors = metadata_extractors
        self.alias_strategies = alias_strategies
        self.permissions = permissions

    def upload_new_document(self, request: UploadRequest) -> UploadResult:
        """Create a new document chain when no name match exists."""
        raise NotImplementedError

    def upload_new_version(self, document_id: UUID, request: UploadRequest) -> UploadResult:
        """Add version to an existing chain after compatibility validation."""
        raise NotImplementedError

    def validate_filename_compatibility(self, document: Document, source_filename: str) -> bool:
        """Used by 'Upload new version' UI action before version creation."""
        raise NotImplementedError

    def try_match_existing_document(self, request: UploadRequest) -> list[Document]:
        """Return candidates to confirm user intent before linking versions."""
        raise NotImplementedError

    def handle_duplicate_upload(self, document_id: UUID, content_hash: str) -> UploadResult:
        """Return existing version reference instead of creating duplicate."""
        raise NotImplementedError

    def transition_status(
        self,
        *,
        document_id: UUID,
        actor_user_id: int,
        target_status: DocumentStatus,
        action_comment: str,
        allow_without_comment: bool,
    ) -> Document:
        """Workflow transition with explicit comment semantics from UI."""
        raise NotImplementedError

    def set_document_explanation(self, document_id: UUID, explanation: str, actor_user_id: int) -> None:
        """Update global explanation shown with current version."""
        raise NotImplementedError

    def add_discussion_message(
        self, *, version_id: UUID, author_user_id: int, message: str
    ) -> DiscussionMessage:
        """Discussion is version-scoped and does not replace document explanation."""
        raise NotImplementedError

    def mark_invalid_after_parse_failure(
        self, *, document: Document, version: DocumentVersion, parse_error: str
    ) -> Document:
        """Move document to INVALID while keeping uploaded version artifact."""
        raise NotImplementedError

