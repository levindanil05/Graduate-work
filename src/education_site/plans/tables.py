import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from documents.models import DocumentVersion
from documents.workflow_ui import has_allowed_transitions


class ActionsColumn(tables.Column):
    def render(self, value, record: DocumentVersion):
        open_url = reverse('plans:document_detail', args=[record.document_id])
        links = [format_html('<a href="{}">Открыть</a>', open_url)]
        if has_allowed_transitions(record.status):
            transition_url = reverse('plans:transition_status', args=[record.document_id])
            links.append(format_html('<a href="{}?next=/">Статус</a>', transition_url))
        return mark_safe(' | '.join(str(link) for link in links))


class PlxDocumentTable(tables.Table):
    storage_key = tables.Column(verbose_name='Файл')
    direction_code = tables.Column(
        accessor='direction_code',
        verbose_name='Код направления',
        order_by='extracted_metadata__direction_code',
    )
    direction = tables.Column(
        accessor='direction',
        verbose_name='Направление',
        order_by='extracted_metadata__direction',
    )
    profile = tables.Column(
        accessor='profile',
        verbose_name='Профиль',
        order_by='extracted_metadata__profile',
    )
    faculty = tables.Column(
        accessor='faculty',
        verbose_name='Факультет',
        order_by='extracted_metadata__faculty',
    )
    department = tables.Column(
        accessor='department',
        verbose_name='Кафедра',
        order_by='extracted_metadata__department',
    )
    year_start = tables.Column(
        accessor='year_start',
        verbose_name='Год',
        order_by='extracted_metadata__year_start',
    )
    qualification = tables.Column(
        accessor='qualification',
        verbose_name='Квалификация',
        order_by='extracted_metadata__qualification',
    )
    status = tables.Column(
        verbose_name='Статус',
        accessor='get_status_display',
        order_by='status',
    )
    updated_at = tables.DateTimeColumn(verbose_name='Обновлён', format='d.m.Y H:i')
    actions = ActionsColumn(empty_values=(), verbose_name='Действия', orderable=False)

    class Meta:
        model = DocumentVersion
        fields = (
            'storage_key',
            'direction_code',
            'direction',
            'profile',
            'faculty',
            'department',
            'year_start',
            'qualification',
            'status',
            'updated_at',
            'actions',
        )
