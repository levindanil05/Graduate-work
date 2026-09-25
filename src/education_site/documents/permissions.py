from __future__ import annotations

from documents.entities import Document, DocumentVersion, VersionStatus


class AllowAllPermissionService:
    """Legacy: all actions allowed (тесты / аварийный режим)."""

    def can_upload_version(self, user_id: int, document: Document) -> bool:
        return True

    def can_transition(
        self, user_id: int, version: DocumentVersion, to_status: VersionStatus
    ) -> bool:
        return True

    def can_trash(self, user_id: int, document: Document) -> bool:
        return True

    def can_restore(self, user_id: int, document: Document) -> bool:
        return True

    def can_hard_delete(self, user_id: int, document: Document) -> bool:
        return True

    def can_edit_document(self, user_id: int, document: Document | None = None) -> bool:
        return True

    def can_manage_sync(self, user_id: int) -> bool:
        return True
