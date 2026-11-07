from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.decorators import sync_required
from external_sync.models import ExternalConnection, ExternalSyncSettings, SyncRun, SyncRunStatus
from external_sync.services.queue_mode import encode_queue_idempotency_key
from external_sync.services.diagnostics import VERDICT_LABELS, run_connection_diagnostics


@login_required
def plan_add(request):
    """Добавление нового плана (через админку documents)."""
    return redirect('admin:documents_document_changelist')


@sync_required
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
        if mode not in {'full', 'pull', 'push'}:
            mode = 'full'
        SyncRun.objects.create(
            connection=selected,
            status=SyncRunStatus.QUEUED,
            idempotency_key=encode_queue_idempotency_key(mode),
        )
        messages.success(request, 'Синхронизация поставлена в очередь. Обработка идёт в фоне.')
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


@sync_required
@require_http_methods(['GET', 'POST'])
def connection_diagnostics(request):
    connections = ExternalConnection.objects.order_by('slug')
    selected_slug = request.GET.get('connection') or request.POST.get('connection')
    if not selected_slug and connections.exists():
        selected_slug = connections.first().slug
    selected = connections.filter(slug=selected_slug).first()
    report = None

    if request.method == 'POST' and selected:
        report = run_connection_diagnostics(selected)
        if report.verdict == 'ok':
            messages.success(request, 'Диагностика завершена без ошибок.')
        elif report.verdict == 'degraded':
            messages.warning(request, 'Диагностика завершена с предупреждениями.')
        else:
            messages.error(request, 'Диагностика обнаружила ошибки.')

    return render(
        request,
        'plans/external_sync_diagnostics.html',
        {
            'connections': connections,
            'selected_connection': selected,
            'report': report,
            'verdict_label': VERDICT_LABELS.get(report.verdict, '') if report else '',
        },
    )


@sync_required
def sync_run_detail(request, run_id):
    sync_run = get_object_or_404(SyncRun.objects.select_related('connection'), pk=run_id)
    return render(
        request,
        'plans/sync_run_detail.html',
        {
            'sync_run': sync_run,
        },
    )


@sync_required
def sync_yandex(request):
    """Устаревший URL — перенаправление на экран синхронизации."""
    return redirect('plans:external_sync_dashboard')
