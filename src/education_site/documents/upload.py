from __future__ import annotations

from pathlib import Path
from uuid import UUID

from documents.entities import DocumentType
from documents.factory import build_document_service
from documents.infra.hashing import HashingService
from documents.infra.storage import UserfilesStoragePort
from documents.services import UploadRequest, UploadResult
from documents.strategies import PlxNamingStrategy


def ingest_plx_file(
    *,
    file_path: Path,
    storage_key: str,
    user_id: int = 0,
    document_id: UUID | None = None,
    force_new: bool = False,
    auto_link_single_match: bool = True,
) -> UploadResult:
    """Upload PLX through domain service: matching, hash-dedup, parse → invalid."""
    service = build_document_service()
    request = UploadRequest(
        user_id=user_id,
        document_type=DocumentType.PLX,
        file_path=file_path,
        source_filename=storage_key.replace('\\', '/'),
    )

    if document_id is not None:
        return service.upload_new_version(document_id, request)

    if not force_new and auto_link_single_match:
        matches = service.try_match_existing_document(request)
        if len(matches) == 1:
            return service.upload_new_version(matches[0].id, request)

    return service.upload_new_document(request)


def plan_status_to_version_status(plan_status: str) -> str:
    mapping = {
        'draft': 'new',
        'review': 'on_review',
        'approved': 'approved',
        'rejected': 'needs_fix',
    }
    return mapping.get(plan_status, 'new')


def migrate_educational_plan_record(plan, *, storage: UserfilesStoragePort, hasher: HashingService) -> None:
    """Create Document + v1 from legacy EducationalPlan row."""
    from documents import models as orm

    if orm.DocumentVersion.objects.filter(storage_key=plan.source_path).exists():
        return

    strategy = PlxNamingStrategy()
    source_name = Path(plan.source_path).name
    canonical = plan.source_path
    aliases = set(strategy.build_aliases(plan.source_path))

    document = orm.Document.objects.create(
        document_type=orm.DocumentType.PLX,
        canonical_name=canonical,
        explanation=plan.comments or '',
    )
    for alias in aliases:
        orm.DocumentAlias.objects.get_or_create(
            alias=alias,
            defaults={'document': document},
        )

    abs_path = storage.resolve_path(plan.source_path)
    content_hash = hasher.hash_file(abs_path) if abs_path.exists() else ''

    metadata = {
        'direction_code': plan.direction_code,
        'direction': plan.direction,
        'faculty': plan.faculty,
        'department': plan.department,
        'year_start': plan.year_start,
        'qualification': plan.qualification,
    }

    version = orm.DocumentVersion.objects.create(
        document=document,
        status=plan_status_to_version_status(plan.status),
        version_number=1,
        source_filename=source_name,
        storage_key=plan.source_path,
        content_hash=content_hash,
        extracted_metadata=metadata,
    )
    document.current_version = version
    document.save(update_fields=['current_version', 'updated_at'])
