from __future__ import annotations

from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from accounts.decorators import user_can_edit_document, user_can_upload
from accounts.permissions import (
    user_can_hard_delete,
    user_can_update_of_type,
    user_can_view_of_type,
)
from documents.entities import DocumentVersion as DomainVersion
from documents.entities import VersionStatus
from documents.factory import build_document_service
from documents.infra.storage import build_storage_port
from documents.models import DiscussionThread, Document, DocumentVersion, WorkflowTransition
from documents.services import DomainValidationError
from documents.workflow_ui import (
    list_allowed_transitions_for_user,
    target_status_label,
    transition_label,
)
from external_sync.models import ExternalReplica
from external_sync.registry import ConnectionRegistry
from external_sync.ui_labels import replica_role_label, replica_sync_state_label
from plans.canonical_edit import (
    NAMING_FIELD_SPECS,
    build_preview_name,
    check_canonicity,
    naming_values_from_meta,
    parse_naming_post,
)


def _get_document(document_id: UUID) -> Document:
    return get_object_or_404(
        Document.objects.select_related('current_version', 'approved_version').prefetch_related(
            'versions',
            'aliases',
        ),
        pk=document_id,
    )


def _workflow_history(document: Document):
    version_ids = document.versions.values_list('id', flat=True)
    return (
        WorkflowTransition.objects.filter(document_version_id__in=version_ids)
        .select_related('document_version')
        .order_by('-created_at')
    )


def _discussion_messages(version: DocumentVersion | None):
    if version is None:
        return []
    try:
        thread = DiscussionThread.objects.get(document_version=version)
    except DiscussionThread.DoesNotExist:
        return []
    return thread.messages.order_by('created_at')


def _naming_form_fields(values: dict[str, str]):
    return [
        {
            'key': spec.key,
            'label': spec.label,
            'choices': spec.choices,
            'value': values.get(spec.key, ''),
        }
        for spec in NAMING_FIELD_SPECS
    ]


def _domain_version_stub(orm_version: DocumentVersion) -> DomainVersion:
    return DomainVersion(
        id=orm_version.id,
        document_id=orm_version.document_id,
        status=VersionStatus(orm_version.status),
        version_number=orm_version.version_number,
        source_filename=orm_version.source_filename,
        storage_key=orm_version.storage_key,
        content_hash=orm_version.content_hash,
    )


def _transitions_for_request(
    request: HttpRequest,
    current: DocumentVersion | None,
    *,
    document_type: str | None = None,
):
    if current is None or not request.user.is_authenticated:
        return []
    rules = list_allowed_transitions_for_user(
        current.status,
        user_id=request.user.pk,
        version=_domain_version_stub(current),
        document_type=document_type,
    )
    return [
        (rule, transition_label(rule, document_type=document_type))
        for rule in rules
    ]


def _direct_download_urls_for_document(
    request: HttpRequest,
    document: Document,
) -> dict:
    """Прямые ссылки Nextcloud для текущей и утверждённой редакции (без копирования файла)."""
    from accounts.permissions import RolePermissionService

    urls: dict[str, str] = {}
    if not request.user.is_authenticated:
        return urls
    if document.current_version and document.current_version.status == VersionStatus.TRASHED.value:
        return urls

    permissions = RolePermissionService()
    storage = build_storage_port()
    candidates = []
    if document.current_version is not None:
        candidates.append(document.current_version)
    if (
        document.approved_version is not None
        and (
            document.current_version is None
            or document.approved_version_id != document.current_version_id
        )
    ):
        candidates.append(document.approved_version)

    for version in candidates:
        if not version.storage_key:
            continue
        if not permissions.can_download(request.user.pk, version):
            continue
        try:
            url = storage.direct_download_url(version.storage_key, version.source_filename)
        except Exception:  # noqa: BLE001
            url = None
        if url:
            urls[str(version.id)] = url
    return urls


@login_required
def document_detail(request: HttpRequest, document_id: UUID) -> HttpResponse:
    document = _get_document(document_id)
    current = document.current_version
    can_edit = user_can_edit_document(request)
    if document.document_type == 'plx':
        can_upload = user_can_upload(request)
    else:
        can_upload = user_can_update_of_type(request.user.pk, document.document_type)
    can_view = user_can_view_of_type(request.user.pk, document.document_type)
    if not can_view:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied('Недостаточно прав для просмотра этого документа')
    can_hard_delete = user_can_hard_delete(request.user.pk if request.user.is_authenticated else None)
    transition_choices = _transitions_for_request(
        request, current, document_type=document.document_type
    )
    open_name_editor = request.GET.get('edit_name') == '1'
    naming_values = naming_values_from_meta(
        (current.extracted_metadata if current else None) or {}
    )
    naming_from_post = False

    if request.method == 'POST' and can_edit:
        action = request.POST.get('action')
        service = build_document_service()

        if action == 'explanation':
            try:
                service.set_document_explanation(
                    document.id,
                    request.POST.get('explanation', ''),
                    request.user.id,
                )
                messages.success(request, _('Explanation saved'))
            except DomainValidationError as exc:
                messages.error(request, str(exc))
            return redirect(f'{request.path}?tab=status')

        if action == 'canonical_rename' and current and can_upload:
            naming_values = parse_naming_post(request.POST)
            naming_from_post = True
            try:
                new_name = service.apply_plx_canonical_rename(
                    document_id=document.id,
                    field_values=naming_values,
                    actor_user_id=request.user.id,
                    allow_large_deviation=request.POST.get('allow_large_deviation') == 'on',
                )
                messages.success(
                    request,
                    _('Name updated and file renamed to «%(name)s»') % {'name': new_name},
                )
                return redirect(f'{request.path}?tab=status')
            except DomainValidationError as exc:
                messages.error(request, str(exc))
                open_name_editor = True

        if action == 'discussion' and current:
            try:
                service.add_discussion_message(
                    version_id=current.id,
                    author_user_id=request.user.id,
                    message=request.POST.get('message', ''),
                )
                messages.success(request, _('Discussion message added'))
            except DomainValidationError as exc:
                messages.error(request, str(exc))
            return redirect(f'{request.path}?tab=discussion')

    document = _get_document(document_id)
    current = document.current_version
    meta = (current.extracted_metadata if current else None) or {}
    is_plx = document.document_type == 'plx'
    canonicity = None
    naming_form_fields = []
    preview_canonical_name = ''
    if is_plx:
        canonicity = check_canonicity(
            source_filename=(current.source_filename if current else ''),
            document_canonical_name=document.canonical_name,
            meta=meta,
        )
        if not naming_from_post:
            naming_values = naming_values_from_meta(meta)
        naming_form_fields = _naming_form_fields(naming_values)
        preview_canonical_name = build_preview_name(naming_values)

    tab = request.GET.get('tab', 'status')
    from accounts.permissions import user_can_see_external_replicas

    show_external = user_can_see_external_replicas(request.user.pk)
    allowed_tabs = {
        'status',
        'versions',
        'workflow',
        'discussion',
        'metadata',
    }
    from documents.document_types import companion_slots_for

    if companion_slots_for(document.document_type):
        allowed_tabs.add('companions')
    if show_external:
        allowed_tabs.add('external')
    if tab not in allowed_tabs:
        tab = 'status'

    replica_rows = []
    if show_external:
        version_ids = list(document.versions.values_list('id', flat=True))
        external_replicas = (
            ExternalReplica.objects.filter(version_id__in=version_ids)
            .select_related('connection', 'version')
            .order_by('connection__name', 'role', 'remote_path')
        )
        registry = ConnectionRegistry()
        for replica in external_replicas:
            browse_url = None
            try:
                provider = registry.build_provider(replica.connection)
                browse_url = provider.browse_url(replica.remote_path)
            except Exception:  # noqa: BLE001
                browse_url = None
            replica_rows.append(
                {
                    'replica': replica,
                    'connection_name': replica.connection.name,
                    'role_label': replica_role_label(replica.role),
                    'state_label': replica_sync_state_label(replica.sync_state),
                    'browse_url': browse_url,
                }
            )

    from helpcenter.views import process_diagram_context

    display_name = (
        current.source_filename
        if current and current.source_filename
        else document.canonical_name
    )

    from django.urls import reverse

    direct_download_urls = _direct_download_urls_for_document(request, document)
    current_download_href = None
    if current is not None:
        current_download_href = direct_download_urls.get(str(current.id)) or reverse(
            'plans:download_current',
            args=[document.id],
        )

    version_rows = []
    for version in document.versions.order_by('-version_number'):
        href = direct_download_urls.get(str(version.id)) or reverse(
            'plans:download_version',
            args=[document.id, version.id],
        )
        version_rows.append({'version': version, 'download_href': href})

    from plans.companion_views import companion_slots_context
    from documents.relations import current_relation_for_companion

    companion_slots = companion_slots_context(document, request.user.pk)
    related_to = current_relation_for_companion(document)

    return render(
        request,
        'plans/document_detail.html',
        {
            'document': document,
            'display_name': display_name,
            'current_version': current,
            'versions': document.versions.order_by('-version_number'),
            'version_rows': version_rows,
            'workflow_history': _workflow_history(document),
            'discussion_messages': _discussion_messages(current),
            'transition_choices': transition_choices,
            'tab': tab,
            'canonicity': canonicity,
            'naming_form_fields': naming_form_fields,
            'preview_canonical_name': preview_canonical_name,
            'open_name_editor': open_name_editor,
            'external_replica_rows': replica_rows,
            'show_external_replicas': show_external,
            'approved_version': document.approved_version,
            'can_edit': can_edit,
            'can_upload': can_upload,
            'can_hard_delete': can_hard_delete,
            'current_download_href': current_download_href,
            'companion_slots': companion_slots,
            'related_to': related_to,
            'process_diagram': process_diagram_context(
                current_status=current.status if current else None,
                include_transitions=False,
            ),
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def transition_status(request: HttpRequest, document_id: UUID) -> HttpResponse:
    document = _get_document(document_id)
    current = document.current_version
    if current is None:
        raise Http404('У документа нет текущей редакции')

    domain_version = _domain_version_stub(current)
    doc_type = document.document_type
    allowed = list_allowed_transitions_for_user(
        current.status,
        user_id=request.user.pk,
        version=domain_version,
        document_type=doc_type,
    )
    transition_choices = [
        (
            rule,
            transition_label(rule, document_type=doc_type),
            target_status_label(rule.to_status, document_type=doc_type),
        )
        for rule in allowed
    ]
    next_url = request.GET.get('next') or request.POST.get('next') or ''

    if request.method == 'POST':
        target = request.POST.get('target_status', '').strip()
        comment = request.POST.get('action_comment', '')
        allow_without = request.POST.get('allow_without_comment') == 'on'

        try:
            service = build_document_service()
            service.transition_version_status(
                version_id=current.id,
                actor_user_id=request.user.id,
                target_status=VersionStatus(target),
                action_comment=comment,
                allow_without_comment=allow_without,
            )
            messages.success(
                request,
                f'Статус изменён: '
                f'{target_status_label(current.status, document_type=doc_type)} → '
                f'{target_status_label(target, document_type=doc_type)}',
            )
            if next_url.startswith('/'):
                return redirect(next_url)
            return redirect('plans:document_detail', document_id=document.id)
        except (DomainValidationError, ValueError) as exc:
            messages.error(request, str(exc))

    return render(
        request,
        'plans/transition.html',
        {
            'document': document,
            'current_version': current,
            'transition_choices': transition_choices,
            'next_url': next_url,
            'preselected_target': request.GET.get('target', ''),
        },
    )


def _file_response(version: DocumentVersion) -> HttpResponse:
    storage = build_storage_port()
    if not version.storage_key or not storage.exists(version.storage_key):
        raise Http404('Файл не найден')
    direct = storage.direct_download_url(version.storage_key, version.source_filename)
    if direct:
        response = HttpResponseRedirect(direct)
        response['Cache-Control'] = 'no-store'
        return response
    try:
        stream = storage.open_stream(version.storage_key)
    except FileNotFoundError as exc:
        raise Http404('Файл не найден') from exc
    return FileResponse(
        stream,
        as_attachment=True,
        filename=version.source_filename,
    )


@login_required
def download_current(request: HttpRequest, document_id: UUID) -> HttpResponse:
    from accounts.permissions import RolePermissionService
    from django.core.exceptions import PermissionDenied

    document = _get_document(document_id)
    if document.current_version is None:
        raise Http404('Нет актуальной редакции')
    version = document.current_version
    if not RolePermissionService().can_download(request.user.pk, version):
        raise PermissionDenied('Скачивание недоступно')
    return _file_response(version)


@login_required
def download_version(request: HttpRequest, document_id: UUID, version_id: UUID) -> HttpResponse:
    from accounts.permissions import RolePermissionService
    from django.core.exceptions import PermissionDenied

    version = get_object_or_404(DocumentVersion, pk=version_id, document_id=document_id)
    if not RolePermissionService().can_download(request.user.pk, version):
        raise PermissionDenied('Скачивание недоступно')
    return _file_response(version)
