"""Загрузка, перепривязка и реестр компаньонов."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.permissions import (
    user_can_create_of_type,
    user_can_hard_delete,
    user_can_update_of_type,
    user_can_view_of_type,
)
from documents.document_types import (
    companion_slots_for,
    get_spec,
    label_for,
    list_specs,
    slot_for,
)
from documents.factory import build_document_service
from documents.models import Document, DocumentRelation, DocumentVersion
from documents.relations import (
    bind_companion,
    documents_of_type,
    list_companions_for_primary,
    orphan_companion_queryset,
    rebind_companion,
)
from documents.services import DomainValidationError, UploadRequest


def _check_extension(filename: str, document_type: str) -> None:
    spec = get_spec(document_type)
    if not spec.file_extensions:
        return
    lower = filename.lower()
    if not any(lower.endswith(ext.lower()) for ext in spec.file_extensions):
        allowed = ', '.join(spec.file_extensions)
        raise DomainValidationError(f'Допустимые расширения: {allowed}')


@login_required
@require_http_methods(['GET', 'POST'])
def upload_companion_version(request: HttpRequest, document_id: UUID) -> HttpResponse:
    """Новая редакция уже существующего компаньона (не PLX)."""
    companion = get_object_or_404(Document.objects.select_related('current_version'), pk=document_id)
    if companion.document_type == 'plx':
        return redirect(f"{reverse_upload_plx()}?document_id={companion.id}")

    if not user_can_update_of_type(request.user.pk, companion.document_type):
        raise PermissionDenied('Недостаточно прав для загрузки новой редакции')

    if request.method == 'POST':
        uploaded = request.FILES.get('companion_file')
        if not uploaded:
            messages.error(request, 'Выберите файл.')
            return redirect(request.path)
        try:
            _check_extension(uploaded.name or '', companion.document_type)
        except DomainValidationError as exc:
            messages.error(request, str(exc))
            return redirect(request.path)

        suffix = Path(uploaded.name).suffix or ''
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = Path(tmp.name)

        service = build_document_service()
        try:
            service.upload_new_version(
                companion.id,
                UploadRequest(
                    user_id=request.user.pk,
                    document_type=companion.document_type,
                    file_path=tmp_path,
                    source_filename=(uploaded.name or 'file').replace('\\', '/'),
                    change_comment=request.POST.get('change_comment', ''),
                    skip_filename_check=True,
                    link_source_as_alias=True,
                ),
            )
            messages.success(request, 'Новая редакция загружена.')
            return redirect('plans:document_detail', document_id=companion.id)
        except DomainValidationError as exc:
            messages.error(request, str(exc))
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Ошибка загрузки: {exc}')
        finally:
            tmp_path.unlink(missing_ok=True)

    return render(
        request,
        'plans/upload_companion.html',
        {
            'primary': companion,
            'slot': None,
            'slot_label': label_for(companion.document_type),
            'target_version': None,
            'extensions': get_spec(companion.document_type).file_extensions,
            'version_only': True,
        },
    )


def reverse_upload_plx() -> str:
    from django.urls import reverse

    return reverse('plans:upload_plx')


@login_required
@require_http_methods(['GET', 'POST'])
def upload_companion(request: HttpRequest, document_id: UUID) -> HttpResponse:
    primary = get_object_or_404(Document.objects.select_related('current_version'), pk=document_id)
    slot_code = (request.GET.get('slot') or request.POST.get('slot') or '').strip()
    slot = slot_for(primary.document_type, slot_code)
    if slot is None:
        messages.error(request, 'Слот компаньона не настроен для этого документа.')
        return redirect('plans:document_detail', document_id=primary.id)

    if not user_can_create_of_type(request.user.pk, slot.code):
        raise PermissionDenied('Недостаточно прав для загрузки этого вида документа')

    version_id = (request.GET.get('version_id') or request.POST.get('version_id') or '').strip()
    target_version = None
    if slot.anchor == 'edition':
        if version_id:
            target_version = get_object_or_404(
                DocumentVersion, pk=version_id, document_id=primary.id
            )
        elif primary.current_version_id:
            target_version = primary.current_version
        else:
            messages.error(request, 'Нет редакции учебного плана для привязки.')
            return redirect('plans:document_detail', document_id=primary.id)

    if request.method == 'POST':
        uploaded = request.FILES.get('companion_file')
        if not uploaded:
            messages.error(request, 'Выберите файл.')
            return redirect(
                f"{request.path}?slot={slot.code}"
                + (f"&version_id={target_version.id}" if target_version else '')
            )
        try:
            _check_extension(uploaded.name or '', slot.code)
        except DomainValidationError as exc:
            messages.error(request, str(exc))
            return redirect('plans:document_detail', document_id=primary.id)

        suffix = Path(uploaded.name).suffix or ''
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = Path(tmp.name)

        service = build_document_service()
        try:
            result = service.upload_new_document(
                UploadRequest(
                    user_id=request.user.pk,
                    document_type=slot.code,
                    file_path=tmp_path,
                    source_filename=(uploaded.name or 'file').replace('\\', '/'),
                    change_comment=request.POST.get('change_comment', ''),
                )
            )
            companion = Document.objects.get(pk=result.document_id)
            bind_companion(
                companion=companion,
                primary=primary,
                slot_code=slot.code,
                target_version=target_version,
            )
            messages.success(request, 'Файл загружен и привязан.')
            return redirect('plans:document_detail', document_id=primary.id)
        except DomainValidationError as exc:
            messages.error(request, str(exc))
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Ошибка загрузки: {exc}')
        finally:
            tmp_path.unlink(missing_ok=True)

    return render(
        request,
        'plans/upload_companion.html',
        {
            'primary': primary,
            'slot': slot,
            'slot_label': label_for(slot.code),
            'target_version': target_version,
            'extensions': get_spec(slot.code).file_extensions,
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def rebind_companion_view(request: HttpRequest, document_id: UUID) -> HttpResponse:
    primary = get_object_or_404(Document, pk=document_id)
    slot_code = (request.GET.get('slot') or request.POST.get('slot') or '').strip()
    slot = slot_for(primary.document_type, slot_code)
    if slot is None or slot.anchor != 'edition':
        messages.error(request, 'Перепривязка доступна только для слотов с якорем «редакция».')
        return redirect('plans:document_detail', document_id=primary.id)

    if not user_can_update_of_type(request.user.pk, slot.code):
        raise PermissionDenied('Недостаточно прав для перепривязки')

    # Существующие текущие компаньоны этого слота у данного плана (любая редакция).
    existing = (
        DocumentRelation.objects.filter(
            target_document=primary,
            slot_code=slot.code,
            is_current=True,
        )
        .select_related('source_document', 'target_version')
        .order_by('-updated_at')
    )
    editions = primary.versions.exclude(status='trashed').order_by('-version_number')

    if request.method == 'POST':
        relation_id = request.POST.get('relation_id', '').strip()
        version_id = request.POST.get('version_id', '').strip()
        relation = get_object_or_404(DocumentRelation, pk=relation_id, target_document=primary)
        target_version = get_object_or_404(DocumentVersion, pk=version_id, document_id=primary.id)
        try:
            rebind_companion(relation=relation, target_version=target_version)
            messages.success(request, 'Документ перепривязан к выбранной редакции.')
            return redirect('plans:document_detail', document_id=primary.id)
        except DomainValidationError as exc:
            messages.error(request, str(exc))

    return render(
        request,
        'plans/rebind_companion.html',
        {
            'primary': primary,
            'slot': slot,
            'slot_label': label_for(slot.code),
            'existing': existing,
            'editions': editions,
        },
    )


@login_required
def document_type_list(request: HttpRequest, type_code: str) -> HttpResponse:
    try:
        spec = get_spec(type_code)
    except Exception:  # noqa: BLE001
        messages.error(request, 'Неизвестный вид документа.')
        return redirect('plans:plan_list')

    if not user_can_view_of_type(request.user.pk, type_code):
        raise PermissionDenied('Недостаточно прав для просмотра этого вида документов')

    orphans_only = request.GET.get('orphans') == '1'
    queryset = list(documents_of_type(type_code, orphans_only=orphans_only))
    can_hard = user_can_hard_delete(request.user.pk)

    if request.method == 'POST' and can_hard:
        action = request.POST.get('action', '')
        ids = request.POST.getlist('document_ids')
        if action == 'hard_delete' and ids:
            service = build_document_service()
            deleted = 0
            for raw in ids:
                doc = Document.objects.filter(pk=raw, document_type=type_code).first()
                if doc is None:
                    continue
                # Массовое удаление сирот — только документы без текущего главного.
                if orphan_companion_queryset(type_code).filter(pk=doc.pk).exists():
                    try:
                        # Сначала в корзину не требуем: сироты могут быть не в trash —
                        # для простоты удаляем только если current trashed либо принудительно
                        # через сервис после перевода? План: массовое удаление сирот.
                        # Разрешим hard delete сироты напрямую админу.
                        current = doc.current_version
                        if current and current.status != 'trashed':
                            from documents.entities import VersionStatus as DomStatus

                            service.transition_version_status(
                                version_id=current.id,
                                actor_user_id=request.user.pk,
                                target_status=DomStatus.TRASHED,
                                action_comment='Перед удалением сироты',
                                allow_without_comment=True,
                            )
                        service.hard_delete_document(
                            document_id=doc.id,
                            actor_user_id=request.user.pk,
                        )
                        deleted += 1
                    except DomainValidationError as exc:
                        messages.error(request, str(exc))
            if deleted:
                messages.success(request, f'Удалено документов: {deleted}.')
            return redirect(f"{request.path}?orphans=1" if orphans_only else request.path)

    rows = []
    for doc in queryset:
        rel = (
            DocumentRelation.objects.filter(source_document=doc, is_current=True)
            .select_related('target_document', 'target_version')
            .first()
        )
        rows.append({'document': doc, 'relation': rel})

    return render(
        request,
        'plans/document_type_list.html',
        {
            'spec': spec,
            'rows': rows,
            'orphans_only': orphans_only,
            'can_hard_delete': can_hard,
            'type_codes': [(s.code, s.label) for s in list_specs() if s.code != 'plx'],
        },
    )


def companion_slots_context(primary: Document, user_id: int | None) -> list[dict]:
    """Данные слотов для карточки главного документа."""
    views = list_companions_for_primary(primary, version=primary.current_version)
    by_slot: dict[str, list] = {}
    for view in views:
        by_slot.setdefault(view.relation.slot_code, []).append(view)

    slots = []
    for slot in companion_slots_for(primary.document_type):
        try:
            get_spec(slot.code)
        except Exception:  # noqa: BLE001
            continue
        can_update = user_can_update_of_type(user_id, slot.code) if user_id else False
        can_create = user_can_create_of_type(user_id, slot.code) if user_id else False
        can_view = user_can_view_of_type(user_id, slot.code) if user_id else False
        slots.append(
            {
                'slot': slot,
                'label': label_for(slot.code),
                'relations': by_slot.get(slot.code, []),
                'can_create': can_create,
                'can_update': can_update,
                'can_view': can_view,
            }
        )
    return slots
