from __future__ import annotations

from pathlib import Path
from uuid import UUID

from documents.entities import DocumentType
from documents.factory import build_document_service
from documents.services import UploadRequest, UploadResult


def ingest_plx_file(
    *,
    file_path: Path,
    storage_key: str,
    user_id: int = 0,
    document_id: UUID | None = None,
    force_new: bool = False,
    auto_link_single_match: bool = True,
    skip_filename_check: bool = False,
    link_source_as_alias: bool = False,
) -> UploadResult:
    """Upload PLX through domain service: matching, hash-dedup, parse → invalid."""
    service = build_document_service()
    request = UploadRequest(
        user_id=user_id,
        document_type=DocumentType.PLX,
        file_path=file_path,
        source_filename=storage_key.replace('\\', '/'),
        skip_filename_check=skip_filename_check,
        link_source_as_alias=link_source_as_alias or skip_filename_check,
    )

    if document_id is not None:
        return service.upload_new_version(document_id, request)

    if not force_new and auto_link_single_match:
        suggestions = service.suggest_document_matches(request).suggestions
        exact = [s for s in suggestions if s.reason in ('filename_exact', 'canonical_exact')]
        if len(exact) == 1:
            link_request = UploadRequest(
                user_id=request.user_id,
                document_type=request.document_type,
                file_path=request.file_path,
                source_filename=request.source_filename,
                change_comment=request.change_comment,
                skip_filename_check=exact[0].reason == 'canonical_exact',
                link_source_as_alias=True,
            )
            return service.upload_new_version(exact[0].document_id, link_request)

    return service.upload_new_document(request)
