"""Проверка работоспособности сервиса."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse


def healthz(request: HttpRequest) -> JsonResponse:
    status = {'status': 'ok', 'checks': {}}
    http_status = 200

    try:
        connection.ensure_connection()
        status['checks']['database'] = 'ok'
    except Exception as exc:  # noqa: BLE001
        status['checks']['database'] = f'error: {exc}'
        status['status'] = 'degraded'
        http_status = 503

    backend = getattr(settings, 'STORAGE_BACKEND', 'local')
    status['checks']['storage_backend'] = backend

    if backend == 'nextcloud':
        try:
            from documents.infra.storage_nextcloud import NextcloudStoragePort

            storage = NextcloudStoragePort()
            probe_key = '_healthz/probe.txt'
            temp_dir = Path(settings.NEXTCLOUD_TEMP_DIR)
            temp_dir.mkdir(parents=True, exist_ok=True)
            local = temp_dir / '.healthz-probe.txt'
            local.write_text('ok', encoding='utf-8')
            try:
                storage.save(local, probe_key)
                data = storage.open_binary(probe_key)
                if data != b'ok':
                    raise RuntimeError('probe content mismatch')
                storage.delete(probe_key)
            finally:
                local.unlink(missing_ok=True)
            status['checks']['storage'] = 'ok'
        except Exception as exc:  # noqa: BLE001
            status['checks']['storage'] = f'error: {exc}'
            status['status'] = 'degraded'
            http_status = 503
    else:
        userfiles = Path(settings.USERFILES_ROOT)
        try:
            userfiles.mkdir(parents=True, exist_ok=True)
            probe = userfiles / '.healthz'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink(missing_ok=True)
            status['checks']['userfiles'] = 'ok'
            status['checks']['storage'] = 'ok'
        except Exception as exc:  # noqa: BLE001
            status['checks']['userfiles'] = f'error: {exc}'
            status['checks']['storage'] = f'error: {exc}'
            status['status'] = 'degraded'
            http_status = 503

    return JsonResponse(status, status=http_status)
