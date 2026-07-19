from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from documents.entities import DocumentType
from documents.factory import build_document_service
from documents.models import Document
from documents.services import UploadRequest
from documents.upload import ingest_plx_file
from plans.canonical_edit import check_canonicity

SESSION_UPLOAD_PATH = 'pending_plx_upload_path'
SESSION_UPLOAD_NAME = 'pending_plx_upload_name'
SESSION_UPLOAD_CANON = 'pending_plx_upload_canon'


def _clear_pending_upload(request) -> None:
    pending = request.session.pop(SESSION_UPLOAD_PATH, None)
    request.session.pop(SESSION_UPLOAD_NAME, None)
    request.session.pop(SESSION_UPLOAD_CANON, None)
    if pending and Path(pending).exists():
        Path(pending).unlink()


def _document_needs_name_fix(document_id: UUID) -> bool:
    document = (
        Document.objects.select_related('current_version')
        .filter(pk=document_id)
        .first()
    )
    if document is None or document.current_version is None:
        return False
    status = check_canonicity(
        source_filename=document.current_version.source_filename,
        document_canonical_name=document.canonical_name,
        meta=document.current_version.extracted_metadata or {},
    )
    return not status.is_canonical


def _redirect_after_upload(request, document_id: UUID | None):
    if not document_id:
        return redirect('plans:plan_list')
    url = reverse('plans:document_detail', kwargs={'document_id': document_id})
    if _document_needs_name_fix(document_id):
        messages.warning(
            request,
            _(
                'Uploaded file name does not match the canonical pattern. '
                'Please review and apply the suggested name.'
            ),
        )
        return redirect(f'{url}?edit_name=1')
    return redirect(url)


@staff_member_required
@require_http_methods(['GET', 'POST'])
def upload_plx(request):
    """Загрузка PLX: matching по имени/канону/метаданным, hash-dedup, parse → invalid."""
    service = build_document_service()
    preset_document_id = request.GET.get('document_id', '').strip() or request.POST.get('document_id', '').strip()
    preset_document = None
    if preset_document_id:
        preset_document = get_object_or_404(Document, pk=preset_document_id)

    if request.method == 'POST':
        confirm_id = request.POST.get('confirm_document_id', '').strip()
        force_new = request.POST.get('force_new') == 'on'
        force_new_from_pending = request.POST.get('force_new_from_pending') == '1'
        pending_path = request.session.get(SESSION_UPLOAD_PATH)
        pending_name = request.session.get(SESSION_UPLOAD_NAME)
        target_document_id = UUID(confirm_id) if confirm_id else None

        if preset_document_id and not confirm_id and request.FILES.get('plx_file'):
            target_document_id = UUID(preset_document_id)

        if force_new_from_pending and pending_path:
            result = None
            try:
                result = ingest_plx_file(
                    file_path=Path(pending_path),
                    storage_key=pending_name or Path(pending_path).name,
                    user_id=request.user.id,
                    force_new=True,
                )
                messages.success(request, _('Uploaded: %(message)s (%(status)s)') % {
                    'message': result.message,
                    'status': result.status,
                })
            except Exception as exc:  # noqa: BLE001
                messages.error(request, _('Upload error: %(error)s') % {'error': exc})
            finally:
                _clear_pending_upload(request)
            return _redirect_after_upload(request, result.document_id if result else None)

        if confirm_id and pending_path:
            try:
                result = ingest_plx_file(
                    file_path=Path(pending_path),
                    storage_key=pending_name or Path(pending_path).name,
                    user_id=request.user.id,
                    document_id=UUID(confirm_id),
                    skip_filename_check=True,
                    link_source_as_alias=True,
                )
                messages.success(request, _('Uploaded: %(message)s (%(status)s)') % {
                    'message': result.message,
                    'status': result.status,
                })
            except Exception as exc:  # noqa: BLE001
                messages.error(request, _('Upload error: %(error)s') % {'error': exc})
            finally:
                _clear_pending_upload(request)
            return _redirect_after_upload(request, UUID(confirm_id))

        uploaded = request.FILES.get('plx_file')
        if not uploaded:
            messages.error(request, _('Select a .plx file'))
            return redirect('plans:upload_plx')

        _clear_pending_upload(request)
        suffix = Path(uploaded.name).suffix or '.plx'
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = Path(tmp.name)

        storage_key = uploaded.name.replace('\\', '/')

        try:
            if target_document_id:
                result = ingest_plx_file(
                    file_path=tmp_path,
                    storage_key=storage_key,
                    user_id=request.user.id,
                    document_id=target_document_id,
                    skip_filename_check=True,
                    link_source_as_alias=True,
                )
                messages.success(request, _('Uploaded: %(message)s (%(status)s)') % {
                    'message': result.message,
                    'status': result.status,
                })
                tmp_path.unlink(missing_ok=True)
                return _redirect_after_upload(request, target_document_id)

            if force_new:
                result = ingest_plx_file(
                    file_path=tmp_path,
                    storage_key=storage_key,
                    user_id=request.user.id,
                    force_new=True,
                )
                messages.success(request, _('Uploaded: %(message)s (%(status)s)') % {
                    'message': result.message,
                    'status': result.status,
                })
                tmp_path.unlink(missing_ok=True)
                return _redirect_after_upload(request, result.document_id)

            upload_request = UploadRequest(
                user_id=request.user.id,
                document_type=DocumentType.PLX,
                file_path=tmp_path,
                source_filename=storage_key,
            )
            match_ctx = service.suggest_document_matches(upload_request)
            suggestions = match_ctx.suggestions
            incoming_canon = match_ctx.incoming_canonical_filename

            if suggestions:
                request.session[SESSION_UPLOAD_PATH] = str(tmp_path)
                request.session[SESSION_UPLOAD_NAME] = storage_key
                request.session[SESSION_UPLOAD_CANON] = incoming_canon
                return render(
                    request,
                    'plans/upload_plx.html',
                    {
                        'suggestions': suggestions,
                        'pending_name': storage_key,
                        'pending_canonical': incoming_canon,
                        'preset_document': preset_document,
                    },
                )

            result = ingest_plx_file(
                file_path=tmp_path,
                storage_key=storage_key,
                user_id=request.user.id,
                force_new=True,
            )
            messages.success(request, _('Uploaded: %(message)s (%(status)s)') % {
                'message': result.message,
                'status': result.status,
            })
            tmp_path.unlink(missing_ok=True)
            return _redirect_after_upload(request, result.document_id)
        except Exception as exc:  # noqa: BLE001
            tmp_path.unlink(missing_ok=True)
            messages.error(request, _('Upload error: %(error)s') % {'error': exc})
            if preset_document_id:
                return redirect(f'{request.path}?document_id={preset_document_id}')
            return redirect('plans:upload_plx')

    if request.GET.get('cancel'):
        _clear_pending_upload(request)
        if preset_document_id:
            return redirect('plans:document_detail', document_id=preset_document_id)
        return redirect('plans:upload_plx')

    return render(
        request,
        'plans/upload_plx.html',
        {
            'suggestions': [],
            'pending_name': '',
            'pending_canonical': '',
            'preset_document': preset_document,
        },
    )
