from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from documents.entities import DocumentType
from documents.factory import build_document_service
from documents.services import UploadRequest
from documents.upload import ingest_plx_file

SESSION_UPLOAD_PATH = 'pending_plx_upload_path'
SESSION_UPLOAD_NAME = 'pending_plx_upload_name'


def _clear_pending_upload(request) -> None:
    pending = request.session.pop(SESSION_UPLOAD_PATH, None)
    request.session.pop(SESSION_UPLOAD_NAME, None)
    if pending and Path(pending).exists():
        Path(pending).unlink()


@staff_member_required
@require_http_methods(['GET', 'POST'])
def upload_plx(request):
    """Загрузка PLX: matching, hash-dedup, parse → invalid."""
    service = build_document_service()

    if request.method == 'POST':
        confirm_id = request.POST.get('confirm_document_id', '').strip()
        force_new = request.POST.get('force_new') == 'on'
        pending_path = request.session.get(SESSION_UPLOAD_PATH)
        pending_name = request.session.get(SESSION_UPLOAD_NAME)

        if confirm_id and pending_path:
            try:
                result = ingest_plx_file(
                    file_path=Path(pending_path),
                    storage_key=pending_name,
                    user_id=request.user.id,
                    document_id=UUID(confirm_id),
                )
                messages.success(request, f'Загружено: {result.message} ({result.status})')
            except Exception as exc:
                messages.error(request, f'Ошибка загрузки: {exc}')
            finally:
                _clear_pending_upload(request)
            return redirect('plans:plan_list')

        uploaded = request.FILES.get('plx_file')
        if not uploaded:
            messages.error(request, 'Выберите файл .plx')
            return redirect('plans:upload_plx')

        _clear_pending_upload(request)
        suffix = Path(uploaded.name).suffix or '.plx'
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = Path(tmp.name)

        storage_key = uploaded.name.replace('\\', '/')

        try:
            if force_new:
                result = ingest_plx_file(
                    file_path=tmp_path,
                    storage_key=storage_key,
                    user_id=request.user.id,
                    force_new=True,
                )
                messages.success(request, f'Загружено: {result.message} ({result.status})')
                tmp_path.unlink(missing_ok=True)
                return redirect('plans:plan_list')

            upload_request = UploadRequest(
                user_id=request.user.id,
                document_type=DocumentType.PLX,
                file_path=tmp_path,
                source_filename=storage_key,
            )
            matches = service.try_match_existing_document(upload_request)

            if matches:
                request.session[SESSION_UPLOAD_PATH] = str(tmp_path)
                request.session[SESSION_UPLOAD_NAME] = storage_key
                return render(
                    request,
                    'plans/upload_plx.html',
                    {
                        'matches': matches,
                        'pending_name': storage_key,
                    },
                )

            result = ingest_plx_file(
                file_path=tmp_path,
                storage_key=storage_key,
                user_id=request.user.id,
                force_new=True,
            )
            messages.success(request, f'Загружено: {result.message} ({result.status})')
            tmp_path.unlink(missing_ok=True)
            return redirect('plans:plan_list')
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            messages.error(request, f'Ошибка загрузки: {exc}')
            return redirect('plans:upload_plx')

    if request.GET.get('cancel'):
        _clear_pending_upload(request)
        return redirect('plans:upload_plx')

    return render(request, 'plans/upload_plx.html', {'matches': [], 'pending_name': ''})
