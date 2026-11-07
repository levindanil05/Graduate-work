from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from accounts.decorators import user_can_upload
from documents.models import VersionStatus

from .querysets import current_plx_versions, trashed_plx_versions


@login_required
def home(request: HttpRequest) -> HttpResponse:
    qs = current_plx_versions()
    status_counts = []
    for value, label in VersionStatus.choices:
        if value == VersionStatus.TRASHED:
            continue
        status_counts.append({'value': value, 'label': label, 'count': qs.filter(status=value).count()})
    trash_count = trashed_plx_versions().count()
    return render(
        request,
        'plans/home.html',
        {
            'status_counts': status_counts,
            'total_count': qs.count(),
            'trash_count': trash_count,
            'can_upload': user_can_upload(request),
        },
    )
