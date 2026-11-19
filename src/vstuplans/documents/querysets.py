import django.db.models as models

from documents.models import DocumentVersion


def current_plx_versions():
    """Queryset of published PLX versions for list UI (approved, else current)."""
    return (
        DocumentVersion.objects.filter(document__document_type='plx')
        .filter(
            models.Q(id=models.F('document__approved_version_id'))
            | models.Q(
                document__approved_version__isnull=True,
                id=models.F('document__current_version_id'),
            )
        )
        .select_related('document')
    )
