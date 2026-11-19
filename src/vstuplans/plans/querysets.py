from __future__ import annotations

from documents.models import DocumentVersion, VersionStatus
from documents.querysets import current_plx_versions as _current_plx_versions


def current_plx_versions():
    return _current_plx_versions()


def trashed_plx_versions():
    return (
        DocumentVersion.objects.filter(
            document__document_type='plx',
            status=VersionStatus.TRASHED,
        )
        .select_related('document')
        .order_by('-updated_at')
    )
