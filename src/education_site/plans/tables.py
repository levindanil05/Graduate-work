import django_tables2 as tables

from documents.models import DocumentVersion


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

    class Meta:
        model = DocumentVersion
        fields = (
            'storage_key',
            'direction_code',
            'direction',
            'faculty',
            'department',
            'year_start',
            'qualification',
            'status',
            'updated_at',
        )
