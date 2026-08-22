from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django_tables2 import RequestConfig

from documents.querysets import current_plx_versions
from external_sync.models import ExternalConnection, ExternalSyncSettings, SyncRun

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
@require_http_methods(['GET', 'POST'])
def external_sync_dashboard(request):
    connections = ExternalConnection.objects.order_by('slug')
    settings = ExternalSyncSettings.get_solo()
    selected_slug = request.GET.get('connection') or request.POST.get('connection')
    if not selected_slug and connections.exists():
        selected_slug = connections.first().slug

    selected = connections.filter(slug=selected_slug).first()
    last_run = None
    if selected:
        last_run = SyncRun.objects.filter(connection=selected).order_by('-created_at').first()

    if request.method == 'POST' and selected:
        mode = request.POST.get('mode', 'full')
        args = ['sync_external_storage', f'--connection={selected.slug}']
        if mode == 'pull':
            args.append('--pull-only')
        elif mode == 'push':
            args.append('--push-only')
        try:
            call_command(*args)
            last_run = SyncRun.objects.filter(connection=selected).order_by('-created_at').first()
            messages.success(request, 'Синхронизация завершена. Отчёт сохранён.')
        except Exception as exc:
            messages.error(request, f'Ошибка синхронизации: {exc}')
        return redirect(f'{request.path}?connection={selected.slug}')

    return render(
        request,
        'plans/external_sync_dashboard.html',
        {
            'connections': connections,
            'selected_connection': selected,
            'sync_settings': settings,
            'last_run': last_run,
        },
    )


@staff_member_required
def sync_run_detail(request, run_id):
    sync_run = get_object_or_404(SyncRun.objects.select_related('connection'), pk=run_id)
    return render(
        request,
        'plans/sync_run_detail.html',
        {
            'sync_run': sync_run,
        },
    )


@staff_member_required
def sync_yandex(request):
    """Устаревший URL — перенаправление на экран синхронизации."""
    return redirect('plans:external_sync_dashboard')
