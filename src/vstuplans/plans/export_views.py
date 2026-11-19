from __future__ import annotations

import csv
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from openpyxl import Workbook

from documents.models import DocumentVersion

from .filters import PlxDocumentFilter
from .views_registry import registry_queryset


EXPORT_COLUMNS = [
    ('source_filename', 'Файл'),
    ('direction_code', 'Код направления'),
    ('direction', 'Направление'),
    ('profile', 'Профиль'),
    ('faculty', 'Факультет'),
    ('department', 'Кафедра'),
    ('year_start', 'Год'),
    ('qualification', 'Квалификация'),
    ('status', 'Статус'),
    ('updated_at', 'Обновлён'),
    ('canonical_name', 'Каноническое имя'),
]


def _filtered_versions(request: HttpRequest):
    queryset = registry_queryset()
    filter_set = PlxDocumentFilter(request.GET, queryset=queryset)
    return filter_set.qs


def _row_values(version: DocumentVersion) -> list:
    return [
        version.source_filename,
        version.direction_code,
        version.direction,
        version.profile,
        version.faculty,
        version.department,
        version.year_start or '',
        version.qualification,
        version.get_status_display(),
        timezone.localtime(version.updated_at).strftime('%d.%m.%Y %H:%M'),
        version.document.canonical_name,
    ]


@login_required
def export_csv(request: HttpRequest) -> HttpResponse:
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = f'attachment; filename="reestr_planov_{stamp}.csv"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')
    writer.writerow([label for _, label in EXPORT_COLUMNS])
    for version in _filtered_versions(request).iterator(chunk_size=200):
        writer.writerow(_row_values(version))
    return response


@login_required
def export_xlsx(request: HttpRequest) -> HttpResponse:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Реестр'
    ws.append([label for _, label in EXPORT_COLUMNS])
    for version in _filtered_versions(request).iterator(chunk_size=200):
        ws.append(_row_values(version))
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="reestr_planov_{stamp}.xlsx"'
    return response
