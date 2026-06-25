from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.shortcuts import redirect, render
from django_tables2 import RequestConfig

from documents.querysets import current_plx_versions

from .filters import PlxDocumentFilter
from .tables import PlxDocumentTable


def plan_list(request):
    """Список учебных планов (текущие версии документов PLX)."""
    queryset = current_plx_versions()
    filter_set = PlxDocumentFilter(request.GET, queryset=queryset)
    table = PlxDocumentTable(filter_set.qs)
    RequestConfig(request, paginate=False).configure(table)
    return render(
        request,
        'plans/plan_list.html',
        {
            'filter': filter_set,
            'table': table,
        },
    )


def plan_add(request):
    """Добавление нового плана (через админку documents)."""
    return redirect('admin:documents_document_changelist')


@staff_member_required
def sync_yandex(request):
    if request.method == 'POST':
        try:
            call_command('update_from_yandex')
            messages.success(request, 'Синхронизация с Яндекс.Диском завершена')
        except Exception as e:
            messages.error(request, f'Ошибка: {e}')
    return redirect(request.META.get('HTTP_REFERER', '/'))
