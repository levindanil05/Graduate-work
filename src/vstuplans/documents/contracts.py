from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, BinaryIO, Protocol
from uuid import UUID

from .entities import (
    DiscussionMessage,
    DiscussionThread,
    Document,
    DocumentType,
    DocumentVersion,
    NameMatchResult,
    VersionStatus,
    WorkflowTransition,
)


class DocumentNamingStrategy(Protocol):
    """Per-type naming/synonym strategy.

    Core idea: each document type can plug a dedicated compatibility strategy.
    """

    def supports(self, document_type: DocumentType) -> bool:
        ...

    def canonicalize(self, filename: str) -> str:
        ...

    def build_aliases(self, filename: str) -> tuple[str, ...]:
        ...

    def is_compatible(self, filename: str, document: Document) -> bool:
        ...

    def find_match(self, filename: str, candidates: list[Document]) -> NameMatchResult:
        ...


class StoragePort(Protocol):
    def save(self, file_path: Path, destination_name: str) -> str:
        ...

    def open_binary(self, storage_key: str) -> bytes:
        ...

    def delete(self, storage_key: str) -> None:
        ...

    def rename(self, storage_key: str, new_basename: str) -> str:
        ...

    def exists(self, storage_key: str) -> bool:
        ...

    def local_copy(self, storage_key: str) -> AbstractContextManager[Path]:
        """Yields a local Path for the object; cleans up temp files when done."""
        ...

    def open_stream(self, storage_key: str) -> BinaryIO:
        ...

    def direct_download_url(self, storage_key: str, filename: str) -> str | None:
        """Public download URL if the backend supports it; otherwise None. Does not copy the file."""
        ...

    def revoke_direct_urls(self, storage_keys: list[str]) -> None:
        """Revoke cached public download links for the given keys (no-op if unsupported)."""
        ...


class MetadataExtractor(Protocol):
    def supports(self, document_type: DocumentType) -> bool:
        ...

    def extract(self, file_path: Path) -> dict[str, Any]:
        ...


class HashingService(Protocol):
    def hash_file(self, file_path: Path) -> str:
        ...


class DocumentRepository(Protocol):
    def get(self, document_id: UUID) -> Document | None:
        ...

    def save(self, document: Document) -> Document:
        ...

    def list_for_type(self, document_type: DocumentType) -> list[Document]:
        ...


class VersionRepository(Protocol):
    def save(self, version: DocumentVersion) -> DocumentVersion:
        ...

    def get(self, version_id: UUID) -> DocumentVersion | None:
        ...

    def get_active_version(self, document_id: UUID) -> DocumentVersion | None:
        ...

    def get_approved_version(self, document_id: UUID) -> DocumentVersion | None:
        ...

    def get_by_hash(self, document_id: UUID, content_hash: str) -> DocumentVersion | None:
        ...

    def list_for_document(self, document_id: UUID) -> list[DocumentVersion]:
        ...


class WorkflowRepository(Protocol):
    def save_transition(self, transition: WorkflowTransition) -> WorkflowTransition:
        ...

    def list_for_version(self, version_id: UUID) -> list[WorkflowTransition]:
        ...


class DiscussionRepository(Protocol):
    def get_or_create_thread(self, version_id: UUID) -> DiscussionThread:
        ...

    def add_message(self, message: DiscussionMessage) -> DiscussionMessage:
        ...

    def list_messages(self, thread_id: UUID) -> list[DiscussionMessage]:
        ...


class PermissionService(Protocol):
    def can_upload_version(self, user_id: int, document: Document) -> bool:
        ...

    def can_transition(self, user_id: int, version: DocumentVersion, to_status: VersionStatus) -> bool:
        ...

    def can_trash(self, user_id: int, document: Document) -> bool:
        ...

    def can_restore(self, user_id: int, document: Document) -> bool:
        ...

    def can_hard_delete(self, user_id: int, document: Document) -> bool:
        ...

    def can_edit_document(self, user_id: int, document: Document | None = None) -> bool:
        ...

    def can_manage_sync(self, user_id: int) -> bool:
        ...

