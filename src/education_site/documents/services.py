from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from .contracts import (
    DiscussionRepository,
    DocumentNamingStrategy,
    DocumentRepository,
    HashingService,
    MetadataExtractor,
    PermissionService,
    StoragePort,
    VersionRepository,
    WorkflowRepository,
)
from .entities import (
    DiscussionMessage,
    Document,
    DocumentType,
    DocumentVersion,
    VersionStatus,
)


@dataclass
class UploadRequest:
    user_id: int
    document_type: DocumentType
    file_path: Path
    source_filename: str
    # Comment about uploaded changes (not discussion message).
    change_comment: str = ""


@dataclass
class UploadResult:
    document_id: UUID
    version_id: UUID | None
    status: str
    message: str


class DocumentApplicationService:
    """Use-case layer contracts only (no implementation yet)."""

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
        naming_strategies: list[DocumentNamingStrategy],
        permissions: PermissionService,
    ) -> None:
        self.documents = documents
        self.versions = versions
        self.workflow = workflow
        self.discussions = discussions
        self.storage = storage
        self.hashing = hashing
        self.metadata_extractors = metadata_extractors
        self.naming_strategies = naming_strategies
        self.permissions = permissions

    def try_match_existing_document(self, request: UploadRequest) -> list[Document]:
        """Resolve candidates to confirm user intent before linking chain."""
        raise NotImplementedError

    def upload_new_document(self, request: UploadRequest) -> UploadResult:
        """Create new document when no matching chain is confirmed."""
        raise NotImplementedError

    def upload_new_version(self, document_id: UUID, request: UploadRequest) -> UploadResult:
        """Upload version to existing document after compatibility checks."""
        raise NotImplementedError

    def validate_filename_compatibility(self, document: Document, source_filename: str) -> bool:
        """Guard for 'Upload new version' action."""
        raise NotImplementedError

    def handle_duplicate_upload(self, document_id: UUID, content_hash: str) -> UploadResult:
        """Idempotency path: no new version, return existing reference."""
        raise NotImplementedError

    def set_document_explanation(self, document_id: UUID, explanation: str, actor_user_id: int) -> None:
        raise NotImplementedError

    def transition_version_status(
        self,
        *,
        version_id: UUID,
        actor_user_id: int,
        target_status: VersionStatus,
        action_comment: str,
        allow_without_comment: bool,
    ) -> DocumentVersion:
        raise NotImplementedError

    def add_discussion_message(
        self, *, version_id: UUID, author_user_id: int, message: str
    ) -> DiscussionMessage:
        raise NotImplementedError

