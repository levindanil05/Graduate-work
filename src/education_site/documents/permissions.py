from __future__ import annotations

from documents.entities import Document, DocumentVersion, VersionStatus


class AllowAllPermissionService:
    """MVP permissions: all actions allowed until auth/roles are implemented."""

    def can_upload_version(self, user_id: int, document: Document) -> bool:
        return True

    def can_transition(self, user_id: int, version: DocumentVersion, to_status: VersionStatus) -> bool:
        return True

    def can_trash(self, user_id: int, document: Document) -> bool:
        return True

    def can_restore(self, user_id: int, document: Document) -> bool:
        return True

    def can_hard_delete(self, user_id: int, document: Document) -> bool:
        return True
