import django.db.models as models

from documents.models import DocumentVersion


def current_plx_versions():
    """Queryset of current PLX document versions for list UI."""
    return (
        DocumentVersion.objects.filter(
            document__document_type='plx',
            id=models.F('document__current_version_id'),
        )
        .select_related('document')
    )
