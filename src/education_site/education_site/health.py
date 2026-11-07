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

    userfiles = Path(settings.USERFILES_ROOT)
    try:
        userfiles.mkdir(parents=True, exist_ok=True)
        probe = userfiles / '.healthz'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        status['checks']['userfiles'] = 'ok'
    except Exception as exc:  # noqa: BLE001
        status['checks']['userfiles'] = f'error: {exc}'
        status['status'] = 'degraded'
        http_status = 503

    return JsonResponse(status, status=http_status)
