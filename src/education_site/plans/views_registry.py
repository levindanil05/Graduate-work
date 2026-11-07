from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django_tables2 import RequestConfig

from accounts.decorators import user_can_upload
from accounts.permissions import RolePermissionService, user_can_hard_delete
from documents.entities import VersionStatus as DomainVersionStatus
from documents.factory import build_document_service
from documents.models import Document, DocumentVersion
from documents.services import DomainValidationError

from .filters import PlxDocumentFilter
from .querysets import current_plx_versions, trashed_plx_versions
from .tables import PlxDocumentTable


def registry_queryset():
    return current_plx_versions()


def _configure_table_pagination(request: HttpRequest, table: PlxDocumentTable) -> tuple[bool, int]:
    show_all = request.GET.get('all') == '1'
    try:
        page_size = int(request.GET.get('page_size', settings.DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        page_size = settings.DEFAULT_PAGE_SIZE
    if show_all:
        RequestConfig(request, paginate=False).configure(table)
    else:
        RequestConfig(request, paginate={'per_page': max(10, min(page_size, 500))}).configure(table)
    return show_all, page_size


@login_required
def plan_list(request: HttpRequest) -> HttpResponse:
    queryset = registry_queryset()
    filter_set = PlxDocumentFilter(request.GET, queryset=queryset)
    table = PlxDocumentTable(filter_set.qs)
    show_all, page_size = _configure_table_pagination(request, table)
    table_rows = table.rows if show_all else table.paginated_rows
    qs = request.GET.copy()
    if 'page' in qs and show_all:
        qs.pop('page')
    query_string = qs.urlencode()
    return render(
        request,
        'plans/plan_list.html',
        {
            'filter': filter_set,
            'table': table,
            'table_rows': table_rows,
            'show_all': show_all,
            'page_size': page_size,
            'query_string': query_string,
            'can_upload': user_can_upload(request),
        },
    )


@login_required
def trash_list(request: HttpRequest) -> HttpResponse:
    queryset = trashed_plx_versions()
    filter_set = PlxDocumentFilter(request.GET, queryset=queryset)
    paginator = Paginator(filter_set.qs, settings.DEFAULT_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    retention = int(getattr(settings, 'TRASH_RETENTION_DAYS', 30))
    now = timezone.now()
    rows = []
    for version in page_obj.object_list:
        days_in_trash = max(0, (now - version.updated_at).days)
        rows.append(
            {
                'version': version,
                'days_in_trash': days_in_trash,
                'days_remaining': max(0, retention - days_in_trash),
            }
        )
    return render(
        request,
        'plans/trash_list.html',
        {
            'filter': filter_set,
            'page_obj': page_obj,
            'rows': rows,
            'trash_retention_days': retention,
            'can_hard_delete': user_can_hard_delete(request.user.pk),
        },
    )


@login_required
@require_http_methods(['POST'])
def hard_delete_document(request: HttpRequest, document_id) -> HttpResponse:
    if not user_can_hard_delete(request.user.pk):
        messages.error(request, 'Недостаточно прав для физического удаления.')
        return redirect('plans:trash_list')

    document = get_object_or_404(Document.objects.select_related('current_version'), pk=document_id)
    current = document.current_version
    if current is None or current.status != DomainVersionStatus.TRASHED.value:
        messages.error(request, 'Удалить можно только документ, целиком находящийся в корзине.')
        return redirect('plans:trash_list')

    service = build_document_service()
    try:
        service.hard_delete_document(document_id=document.pk, actor_user_id=request.user.pk)
        messages.success(request, 'Документ и файлы удалены безвозвратно.')
    except DomainValidationError as exc:
        messages.error(request, str(exc))
    return redirect('plans:trash_list')


@login_required
@require_http_methods(['POST'])
def bulk_registry_action(request: HttpRequest) -> HttpResponse:
    action = request.POST.get('action', '')
    version_ids = request.POST.getlist('version_ids')
    if not version_ids:
        messages.warning(request, 'Не выбрано ни одной версии.')
        return redirect('plans:plan_list')

    service = build_document_service()
    perms = RolePermissionService()
    user_id = request.user.pk
    success = 0
    errors = 0

    for raw_id in version_ids:
        version = DocumentVersion.objects.filter(pk=raw_id).select_related('document').first()
        if version is None:
            errors += 1
            continue
        if action == 'trash':
            target = DomainVersionStatus.TRASHED
        elif action == 'restore':
            target = DomainVersionStatus.NEW
        else:
            messages.error(request, 'Неизвестное действие.')
            return redirect('plans:plan_list')

        if not perms.can_transition(user_id, version, target):
            errors += 1
            continue
        try:
            service.transition_version_status(
                version_id=version.pk,
                actor_user_id=user_id,
                target_status=target,
                action_comment='',
                allow_without_comment=True,
            )
            success += 1
        except Exception:
            errors += 1

    if success:
        from documents.audit import log_action

        log_action(
            action=f'registry_bulk_{action}',
            actor=request.user,
            object_type='document_version',
            metadata={'count': success, 'version_ids': version_ids},
        )
        messages.success(request, f'Обработано версий: {success}.')
    if errors:
        messages.warning(request, f'Не удалось обработать: {errors}.')

    if action == 'restore':
        return redirect('plans:trash_list')
    return redirect('plans:plan_list')
