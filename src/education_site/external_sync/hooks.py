from __future__ import annotations

from uuid import UUID

from django.utils import timezone

from external_sync.models import (
    ExternalConnection,
    ExternalSyncSettings,
    OutboundIntent,
    OutboundKind,
    OutboundStatus,
    WriteMode,
)
from plans.placement_policy import build_active_path_from_metadata


def get_push_connection() -> ExternalConnection | None:
    return (
        ExternalConnection.objects.filter(
            enabled=True,
            write_mode=WriteMode.READ_WRITE,
        )
        .order_by('slug')
        .first()
    )


def on_version_approved(
    *,
    document_id: UUID,
    version_id: UUID,
    previous_approved_id: UUID | None,
) -> None:
    settings = ExternalSyncSettings.get_solo()
    connection = get_push_connection()
    if connection is None:
        return

    from documents.models import DocumentVersion

    version = DocumentVersion.objects.select_related('document').filter(pk=version_id).first()
    if version is None:
        return

    if not settings.external_sync_enabled or not connection.push_enabled:
        status = OutboundStatus.PAUSED_BY_SWITCH
    else:
        status = OutboundStatus.PENDING

    active_path = build_active_path_from_metadata(
        version.extracted_metadata or {},
        version.source_filename,
    )
    OutboundIntent.objects.update_or_create(
        idempotency_key=f'publish:{connection.slug}:{version_id}',
        defaults={
            'connection': connection,
            'version': version,
            'kind': OutboundKind.PUBLISH_ACTIVE,
            'status': status,
            'desired_remote_path': active_path,
        },
    )

    if previous_approved_id:
        OutboundIntent.objects.update_or_create(
            idempotency_key=f'archive:{connection.slug}:{previous_approved_id}',
            defaults={
                'connection': connection,
                'version_id': previous_approved_id,
                'kind': OutboundKind.MOVE_TO_ARCHIVE,
                'status': status,
                'desired_remote_path': '',
            },
        )
