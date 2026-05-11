from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from .entities import (
    DiscussionMessage,
    Document,
    DocumentStatus,
    DocumentType,
    DocumentVersion,
    NameMatchResult,
    WorkflowTransition,
)


class NameAliasStrategy(Protocol):
    """Pluggable strategy per document type for filename normalization/aliases."""

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

    def get_latest(self, document_id: UUID) -> DocumentVersion | None:
        ...

    def get_by_hash(self, document_id: UUID, content_hash: str) -> DocumentVersion | None:
        ...

    def list_for_document(self, document_id: UUID) -> list[DocumentVersion]:
        ...


class WorkflowRepository(Protocol):
    def save_transition(self, transition: WorkflowTransition) -> WorkflowTransition:
        ...

    def list_for_document(self, document_id: UUID) -> list[WorkflowTransition]:
        ...


class DiscussionRepository(Protocol):
    def add_message(self, message: DiscussionMessage) -> DiscussionMessage:
        ...

    def list_messages(self, version_id: UUID) -> list[DiscussionMessage]:
        ...


class PermissionService(Protocol):
    def can_upload_version(self, user_id: int, document: Document) -> bool:
        ...

    def can_transition(self, user_id: int, document: Document, to_status: DocumentStatus) -> bool:
        ...

    def can_trash(self, user_id: int, document: Document) -> bool:
        ...

    def can_restore(self, user_id: int, document: Document) -> bool:
        ...

    def can_hard_delete(self, user_id: int, document: Document) -> bool:
        ...

