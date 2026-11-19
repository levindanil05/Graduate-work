"""Хелперы для ссылок и контекста обратной связи."""
from __future__ import annotations

from urllib.parse import urlencode

from django.http import HttpRequest
from django.urls import reverse


def build_feedback_create_url(
    request: HttpRequest | None = None,
    *,
    document_id: str | None = None,
    source: str | None = None,
) -> str:
    """URL формы создания с source=текущая страница и опциональным document_id."""
    params: dict[str, str] = {}
    if source is not None:
        params['source'] = source
    elif request is not None:
        params['source'] = request.get_full_path()
    if document_id:
        params['document_id'] = str(document_id)
    base = reverse('feedback:create')
    if not params:
        return base
    return f'{base}?{urlencode(params)}'
