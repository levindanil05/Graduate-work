from __future__ import annotations

from uuid import UUID

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from documents.entities import VersionStatus
from documents.factory import build_document_service
from documents.infra.storage import UserfilesStoragePort
from documents.models import DiscussionThread, Document, DocumentVersion, WorkflowTransition
from documents.services import DomainValidationError
from documents.workflow_ui import (
    list_allowed_transitions,
    target_status_label,
    transition_label,
)


def _get_document(document_id: UUID) -> Document:
    return get_object_or_404(
        Document.objects.select_related('current_version').prefetch_related(
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


def document_detail(request: HttpRequest, document_id: UUID) -> HttpResponse:
    document = _get_document(document_id)
    current = document.current_version
    allowed_transitions = list_allowed_transitions(current.status) if current else []
    transition_choices = [(rule, transition_label(rule)) for rule in allowed_transitions]

    if request.method == 'POST' and request.user.is_staff:
        action = request.POST.get('action')
        service = build_document_service()

        if action == 'explanation':
            try:
                service.set_document_explanation(
                    document.id,
                    request.POST.get('explanation', ''),
                    request.user.id,
                )
                messages.success(request, 'Пояснение сохранено')
            except DomainValidationError as exc:
                messages.error(request, str(exc))
            return redirect('plans:document_detail', document_id=document.id)

        if action == 'discussion' and current:
            try:
                service.add_discussion_message(
                    version_id=current.id,
                    author_user_id=request.user.id,
                    message=request.POST.get('message', ''),
                )
                messages.success(request, 'Сообщение добавлено')
            except DomainValidationError as exc:
                messages.error(request, str(exc))
            return redirect(f'{request.path}?tab=discussion')

    tab = request.GET.get('tab', 'versions')
    return render(
        request,
        'plans/document_detail.html',
        {
            'document': document,
            'current_version': current,
            'versions': document.versions.order_by('-version_number'),
            'workflow_history': _workflow_history(document),
            'discussion_messages': _discussion_messages(current),
            'allowed_transitions': allowed_transitions,
            'transition_choices': transition_choices,
            'tab': tab,
            'target_status_label': target_status_label,
            'transition_label': transition_label,
        },
    )


@staff_member_required
@require_http_methods(['GET', 'POST'])
def transition_status(request: HttpRequest, document_id: UUID) -> HttpResponse:
    document = _get_document(document_id)
    current = document.current_version
    if current is None:
        raise Http404('У документа нет текущей версии')

    allowed = list_allowed_transitions(current.status)
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
                f'Статус изменён: {target_status_label(current.status)} → {target_status_label(target)}',
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
            'allowed_transitions': allowed,
            'transition_label': transition_label,
            'target_status_label': target_status_label,
            'next_url': next_url,
        },
    )


def _file_response(version: DocumentVersion) -> FileResponse:
    path = UserfilesStoragePort().resolve_path(version.storage_key)
    if not path.exists():
        raise Http404('Файл не найден на диске')
    return FileResponse(
        path.open('rb'),
        as_attachment=True,
        filename=version.source_filename,
    )


def download_current(request: HttpRequest, document_id: UUID) -> FileResponse:
    document = _get_document(document_id)
    if document.current_version is None:
        raise Http404('Нет актуальной версии')
    return _file_response(document.current_version)


def download_version(request: HttpRequest, document_id: UUID, version_id: UUID) -> FileResponse:
    version = get_object_or_404(DocumentVersion, pk=version_id, document_id=document_id)
    return _file_response(version)
